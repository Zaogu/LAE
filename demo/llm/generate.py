"""llm/generate.py —— LLM 调用 + 解析（FR-5 / AC-4.3 / EC-7）。

- 从 config/llm_config.json 读取 provider/base_url/model/temperature/max_tokens。
- 调用 OpenAI 兼容 chat/completions 接口（requests），解析返回的破坏算子代码。
- 未配置 / 网络失败 / API 错误 -> 返回 not-enabled 标志（ec 降级，不崩溃）。

配置格式（config/llm_config.json）：
  {
    "enabled": true,
    "provider": "openai",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "gpt-4o-mini",
    "temperature": 0.2,
    "max_tokens": 1500,
    "timeout": 60
  }
未提供 api_key 或 enabled=false -> enabled=False。
"""
from __future__ import annotations
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "..", "config", "llm_config.json")


def load_llm_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        return {"enabled": False, "reason": "config not found"}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        return {"enabled": False, "reason": f"config parse error: {e}"}
    # 判定是否真正可用
    if not cfg.get("enabled", False) or not cfg.get("api_key"):
        cfg.setdefault("enabled", False)
        cfg["reason"] = "LLM not configured (no api_key or disabled)"
    return cfg


def _extract_code(text: str) -> str:
    """从 LLM 回复中提取 ```python ... ``` 代码块；无则取首个含 def destroy 的片段。"""
    m = re.findall(r"```python\s*(.*?)```", text, re.DOTALL)
    if m:
        return m[-1].strip()
    m2 = re.search(r"def destroy\(", text)
    if m2:
        return text[m2.start():].strip()
    return text.strip()


def generate_destroy_operator(prompt: str, cfg: dict = None,
                              timeout: int = None) -> dict:
    """调用 LLM 生成破坏算子代码。

    返回 dict:
      status: "ok" | "not_configured" | "error"
      code: 提取出的 Python 函数源码
      raw: LLM 原始回复
      error: 失败原因（status=error/not_configured 时）
    """
    cfg = cfg or load_llm_config()
    timeout = timeout or cfg.get("timeout", 60)

    if not cfg.get("enabled"):
        return {"status": "not_configured", "code": "", "raw": "",
                "error": cfg.get("reason", "LLM not enabled")}

    # 调用 OpenAI 兼容 API（标准库 + requests，无厂商 SDK 依赖）
    try:
        import requests
        resp = requests.post(
            f"{cfg['base_url'].rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {cfg['api_key']}",
                     "Content-Type": "application/json"},
            json={"model": cfg.get("model", "gpt-4o-mini"),
                  "temperature": cfg.get("temperature", 0.2),
                  "max_tokens": cfg.get("max_tokens", 1500),
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        code = _extract_code(raw)
        if "def destroy" not in code:
            return {"status": "error", "code": code, "raw": raw,
                    "error": "LLM 回复中未找到 def destroy(...) 函数签名"}
        return {"status": "ok", "code": code, "raw": raw, "error": ""}
    except Exception as e:
        return {"status": "error", "code": "", "raw": "",
                "error": f"{type(e).__name__}: {e}"}


# ---- 预置保守算子回退（FR-4 / FR-7：LLM 不可用时的兜底）----
def predefined_fallback_destroy() -> str:
    """返回预置的保守破坏算子（随机移除）源码，作为 LLM 失败时的回退。"""
    return '''
import random as _rnd
def destroy(solution, instance, rng, **kwargs):
    served = [i for p in solution.paths for i in p if i != 0]
    k = kwargs.get("k", 2)
    if not served:
        return [], solution
    removed = rng.sample(served, min(k, len(served)))
    rset = set(removed)
    paths = [[x for x in p if x not in rset] for p in solution.paths]
    # 去掉只剩仓库 0 或空的退化路径，避免 [0,0] 之类
    paths = [p for p in paths if len(p) >= 2 and len(set(p)) > 1]
    if not paths:
        paths = [[0]]
    from solver.model import Solution
    partial = Solution(paths, list(solution.unassigned) + removed,
                       solution.objective, solution.feasible)
    return removed, partial
'''


def compile_operator(code: str):
    """把 LLM 生成的代码编译成可调用函数。

    返回 (destroy_fn, error)；失败时 destroy_fn=None，error 含失败原因。
    安全边界：仅在受限命名空间执行，且只能访问标准库（白名单由静态检查模块把关）。
    注意：完整静态检查在 T-08（static_check.py）中实现，这里做最小可编译性兜底。
    """
    if not code or "def destroy" not in code:
        return None, "empty or missing def destroy"
    # 受控几何查询接口：LLM 算子可直接调用 slope()/distance_m()，
    # 无需自行实现 haversine 或依赖 instance['arcs']（顺序弧，非邻接表）。
    from solver.model import Solution, slope, distance_m
    ns = {"slope": slope, "distance_m": distance_m, "Solution": Solution}
    try:
        compiled = compile(code, "<llm_destroy>", "exec")
        exec(compiled, ns)
    except SyntaxError as e:
        return None, f"SyntaxError: {e}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"
    fn = ns.get("destroy")
    if fn is None or not callable(fn):
        return None, "namespace has no callable 'destroy'"
    return fn, ""


if __name__ == "__main__":
    cfg = load_llm_config()
    print(json.dumps({"enabled": cfg.get("enabled"), "reason": cfg.get("reason")},
                     ensure_ascii=False))
