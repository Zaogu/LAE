"""llm/static_check.py —— 静态检查器（FR-6 / NFR-6 / AC-4.2 / EC-3）。

在 LLM 生成的破坏算子注入 ALNS 之前做四道检查：
  1) 语法解析（ast，捕获 SyntaxError）；
  2) 函数签名匹配：必须含 def destroy(solution, instance, rng, **kwargs)；
  3) 禁止模式：文件/网络 I/O、os/sys/subprocess、非白名单 import；
  4) 返回结构提示：函数体应 return (list, Solution-like)（可运行试测，由调用方兜底）。

失败时输出结构化错误（NFR-6 / 供 FR-7 拼回提示词）：
  {"passed": False, "signature_ok": bool, "forbidden_patterns": [..],
   "error_type": "syntax|signature|forbidden|empty", "message": str, "location": str}
通过时 error_type 为 None。
"""
from __future__ import annotations
import ast
import re

# 允许 import 的标准库白名单（设计文档 3.3：禁止文件 I/O、网络请求）
# 允许 import 的标准库白名单（设计文档 3.3：禁止文件 I/O、网络请求）
# 额外允许从本项目 solver.model 导入 Solution（LLM 算子构造部分解时需此工具类，
# 它不是 I/O/网络，属于受控的项目内部工具）。
ALLOWED_IMPORTS = {"math", "random", "solver", "solver.model"}
# 顶层禁止的模块
FORBIDDEN_MODULES = {"os", "sys", "subprocess", "socket", "shutil", "io",
                     "requests", "http", "urllib", "pathlib", "tempfile"}
# 禁止的调用/关键字模式
FORBIDDEN_CALLS = {
    "open", "eval", "exec", "input", "compile",
}
FORBIDDEN_SUBSTR = [
    "__import__", "globals(", "vars(", "breakpoint(",
    "os.", "sys.", "subprocess.", "socket.", "requests.",
    "http.", "urllib.", "shutil.", "pathlib.", "tempfile.",
]
# 期望签名（提示 LLM 与静态检查共用）
EXPECTED_SIG = "destroy(solution, instance, rng, **kwargs)"


def _signature_ok(tree: ast.AST) -> tuple[bool, str]:
    """检查是否存在 def destroy，且形参覆盖 solution/instance/rng（允许 **kwargs）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "destroy":
            args = node.args
            names = [a.arg for a in args.posonlyargs + args.args]
            has_var = args.vararg is not None
            has_kw = args.kwarg is not None
            required = {"solution", "instance", "rng"}
            provided = set(names)
            # **kwargs 可补齐其余形参
            if has_kw:
                provided |= required
            missing = required - provided
            if not missing:
                return True, f"签名匹配 def destroy({EXPECTED_SIG.replace('**kwargs','')})"
            return False, f"destroy 缺少形参 {sorted(missing)}；期望签名: def destroy({EXPECTED_SIG})"
    return False, f"未找到 def destroy(...) 函数；期望签名: def destroy({EXPECTED_SIG})"


def _forbidden(tree: ast.AST, source: str) -> list:
    """扫描禁止模式：import 白名单外的模块、危险调用、危险子串。"""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                top = n.name.split(".")[0]
                if top not in ALLOWED_IMPORTS:
                    found.append(f"import {n.name}（仅允许 {sorted(ALLOWED_IMPORTS)}）")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top not in ALLOWED_IMPORTS:
                found.append(f"from {node.module} import（仅允许 {sorted(ALLOWED_IMPORTS)}）")
        elif isinstance(node, ast.Call):
            name = None
            f = node.func
            if isinstance(f, ast.Name):
                name = f.id
            elif isinstance(f, ast.Attribute):
                name = f.attr
            if name in FORBIDDEN_CALLS:
                found.append(f"调用 {name}() 被禁止（第 {node.lineno} 行）")
    for pat in FORBIDDEN_SUBSTR:
        if pat in source:
            found.append(f"检测到禁止子串 '{pat}'")
    # 去重保持顺序
    seen, out = set(), []
    for x in found:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


def check_operator(code: str) -> dict:
    """对 LLM 生成的破坏算子源码做静态检查，返回结构化结果。"""
    result = {"passed": True, "signature_ok": True, "forbidden_patterns": [],
              "error_type": None, "message": "", "location": ""}
    if not code or not code.strip():
        return _fail(result, "empty", "生成代码为空", "")

    # 1) 语法解析
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return _fail(result, "syntax",
                     f"SyntaxError 第 {e.lineno} 行: {e.msg}", f"line {e.lineno}")

    # 2) 签名
    ok, msg = _signature_ok(tree)
    if not ok:
        return _fail(result, "signature", msg, "def destroy")

    # 3) 禁止模式
    forb = _forbidden(tree, code)
    if forb:
        result["forbidden_patterns"] = forb
        return _fail(result, "forbidden",
                     "检测到禁止模式: " + "; ".join(forb), "call/import")

    result["message"] = "通过静态检查"
    return result


def _fail(result: dict, etype: str, msg: str, loc: str) -> dict:
    result.update({"passed": False, "error_type": etype, "message": msg, "location": loc})
    if etype == "signature":
        result["signature_ok"] = False
    return result


def structured_error(result: dict) -> str:
    """把失败结果转成可拼回提示词的结构化文本（FR-7）。"""
    if result["passed"]:
        return ""
    parts = [f"失败类型: {result['error_type']}",
             f"位置: {result['location'] or 'n/a'}",
             f"说明: {result['message']}"]
    if result["forbidden_patterns"]:
        parts.append("禁止模式: " + "; ".join(result["forbidden_patterns"]))
    parts.append(f"期望接口签名: def destroy({EXPECTED_SIG})")
    return " | ".join(parts)


# ---- 单测（AC-NFR-6 / 验证方式 ≥5 用例）----
def _selftest() -> dict:
    cases = {
        "ok": (
            "def destroy(solution, instance, rng, **kwargs):\n"
            "    import random\n"
            "    served=[i for p in solution.paths for i in p if i!=0]\n"
            "    if not served: return [], solution\n"
            "    r=rng.sample(served,1)\n"
            "    return r, solution\n",
            True, None),
        "syntax_err": ("def destroy(:\n", False, "syntax"),
        "bad_sig": ("def foo(x, y):\n    return 1\n", False, "signature"),
        "no_kwargs_ok": ("def destroy(solution, instance, rng):\n    return [], solution\n",
                         True, None),
        "forbidden_import": ("import os\ndef destroy(s,i,rng,**k):\n    return [],s\n",
                             False, "forbidden"),
        "forbidden_open": ("def destroy(s,i,rng,**k):\n    f=open('x')\n    return [],s\n",
                            False, "forbidden"),
        "empty": ("", False, "empty"),
    }
    rep = {"total": len(cases), "passed": 0, "fail": []}
    for name, (code, want_pass, want_type) in cases.items():
        res = check_operator(code)
        got_pass = res["passed"]
        got_type = res["error_type"]
        ok = (got_pass == want_pass) and (want_type is None or got_type == want_type)
        if ok:
            rep["passed"] += 1
        else:
            rep["fail"].append((name, got_pass, got_type))
    return rep


if __name__ == "__main__":
    r = _selftest()
    print(f"静态检查单测: {r['passed']}/{r['total']} 通过")
    for name, gp, gt in r["fail"]:
        print(f"  [FAIL] {name}: got pass={gp} type={gt}")
    # 演示结构化错误
    demo = check_operator("def destroy(:")
    print("示例结构化错误:", structured_error(demo))
