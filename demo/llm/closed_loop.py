"""T-09 LLM 生成闭环：组织提示词 → 调用 LLM → 静态检查 → 失败重试 ≤3 → 回退预置算子。

职责（FR-5/6/7 / AC-4.2 / EC-3/4）：
  1) 调 LLM 生成破坏算子源码；
  2) 静态检查；失败则把 structured_error 拼回提示词重试，最多 3 次；
  3) 3 次仍失败 → 回退预置保守算子（predefined_fallback_destroy），主循环不中断；
  4) 记录 recovery_action（llm_ok / predefined_fallback / llm_error_fallback / not_configured）
     与每次尝试的结构化日志，供证据链（FR-10）与 H3 量化。

设计要点：
- 无 LLM 配置时（not_configured）直接回退，不触发重试（EC-7/AC-4.3）。
- 每个尝试都产出 dict 记录 {attempt, prompt_hash, status, error_type, message, code_snippet}。
"""
from __future__ import annotations
import os
import time
from typing import Optional, Callable, Dict, Any, List

# 让 llm 包内模块可被任意入口导入
BASE = os.path.dirname(os.path.abspath(__file__))
if os.path.abspath(os.path.join(BASE, "..")) not in __import__("sys").path:
    __import__("sys").path.insert(0, os.path.abspath(os.path.join(BASE, "..")))

from llm.prompt import build_destroy_prompt, instance_features  # type: ignore
from verify.evidence import prompt_hash  # type: ignore
from llm.generate import (
    load_llm_config, generate_destroy_operator, predefined_fallback_destroy,
    compile_operator,
)
from llm.static_check import check_operator, structured_error  # type: ignore
from solver.model import Solution
from solver.alns import destroy_random  # 预置兜底算子之一


MAX_RETRIES = 3  # 静态检查失败最多重试次数（FR-7）


class LLMLoop:
    """LLM 生成闭环：生成 → 检查 → 重试 → 回退。可注入 LLM 调用器做测试/异常注入。"""

    def __init__(self, instance: Dict[str, Any], current_objective: float,
                 current_unassigned: List[int], round_no: int = 1,
                 llm_caller: Optional[Callable] = None,
                 static_checker: Optional[Callable] = None,
                 max_retries: int = MAX_RETRIES):
        self.instance = instance
        self.current_objective = current_objective
        self.current_unassigned = list(current_unassigned)
        self.round_no = round_no
        # 可注入（T-13 异常注入场景用）
        self.llm_caller = llm_caller or generate_destroy_operator
        self._injected = llm_caller is not None  # 注入方提供 LLM（即使全局未配置也走注入路径）
        self.static_checker = static_checker or check_operator
        self.max_retries = max_retries
        self.log: List[Dict[str, Any]] = []
        self.recovery_action: str = "pending"
        self.destroy_fn: Optional[Callable] = None
        self.generated_code: str = ""
        self.generated_code_hash: str = ""
        self.static_check_result: Dict[str, Any] = {}

    # ---- 回退：预置算子编译为可调用函数 ----
    def _fallback(self, reason: str) -> Callable:
        self.recovery_action = reason
        fn, err = compile_operator(predefined_fallback_destroy())
        if fn is None:
            # 连预置算子都编译失败，退到内置 random 破坏（极端兜底）
            self.log.append({"attempt": -1, "status": "fallback_compile_failed",
                             "error": err})
            self.recovery_action = "predefined_fallback"
            return destroy_random
        return fn

    def run(self) -> Dict[str, Any]:
        """执行一次生成闭环，返回可注入 ALNS 的 custom_destroy + 元信息。"""
        prompt = build_destroy_prompt(self.instance,
                                       self.current_objective,
                                       self.current_unassigned,
                                       round_no=self.round_no)

        # 1) LLM 可用性判断：
        #    - 注入式 llm_caller（T-13 异常注入/测试）视为"已配置"，直接走生成+重试循环；
        #    - 默认调用器则读取全局 llm_config.json，无配置时降级（AC-4.3 / EC-7）。
        cfg = load_llm_config()
        if self._injected and not cfg.get("enabled"):
            # 注入场景：即使全局未配置也按"已启用"走注入路径（注入方负责提供 LLM）
            cfg = {**cfg, "enabled": True}
        elif not self._injected and not cfg.get("enabled"):
            self.log.append({"attempt": 0, "status": "not_configured",
                             "error": cfg.get("reason", "LLM not enabled")})
            self.destroy_fn = self._fallback("not_configured")
            self._fill_evidence(prompt, "predefined_fallback")
            return self._result()

        # 2) 生成 + 静态检查 + 重试循环
        last_err = ""
        for attempt in range(1, self.max_retries + 1):
            prompt_try = (prompt + "\n\n【重试 " + str(attempt) +
                          "，上一轮失败：" + last_err + "】") if attempt > 1 else prompt
            res = self.llm_caller(prompt_try, cfg)
            if res.get("status") == "ok":
                code = res["code"]
                chk = self.static_checker(code)
                self.static_check_result = chk
                self.log.append({"attempt": attempt,
                                 "status": "generated",
                                 "static_pass": chk["passed"],
                                 "error_type": chk["error_type"]})
                if chk["passed"]:
                    fn, cerr = compile_operator(code)
                    if fn is not None:
                        self.destroy_fn = fn
                        self.generated_code = code
                        self.generated_code_hash = prompt_hash(code)
                        self.recovery_action = "llm_ok"
                        self._fill_evidence(prompt, "llm_ok")
                        return self._result()
                    # 编译失败按语法/逻辑错误处理，重试
                    last_err = f"编译失败: {cerr}"
                    self.log[-1]["error"] = last_err
                    self.recovery_action = "llm_error_fallback"
                    continue
                else:
                    last_err = structured_error(chk)
                    self.recovery_action = "predefined_fallback"
            else:
                # LLM 调用层失败（网络/参数），直接回退，不消耗重试预算
                self.log.append({"attempt": attempt, "status": res.get("status"),
                                 "error": res.get("error")})
                self.destroy_fn = self._fallback("llm_error_fallback")
                self._fill_evidence(prompt, "llm_error_fallback")
                return self._result()

        # 3) 3 次重试仍失败 → 回退预置保守算子（FR-7 / EC-4）
        self.destroy_fn = self._fallback("predefined_fallback")
        self._fill_evidence(prompt, "predefined_fallback")
        return self._result()

    def _fill_evidence(self, prompt: str, action: str):
        self.generated_code = self.generated_code or predefined_fallback_destroy()
        if not self.generated_code_hash:
            self.generated_code_hash = prompt_hash(self.generated_code)
        self._last_prompt = prompt

    def _result(self) -> Dict[str, Any]:
        return {
            "recovery_action": self.recovery_action,
            "destroy_fn": self.destroy_fn,
            "generated_code": self.generated_code,
            "generated_code_hash": self.generated_code_hash,
            "llm_prompt": getattr(self, "_last_prompt", ""),
            "llm_prompt_hash": prompt_hash(getattr(self, "_last_prompt", "")),
            "static_check": self.static_check_result,
            "attempts_log": self.log,
        }


# ---- 便捷函数：生成闭环并返回可直接注入 ALNSSolver 的 custom_destroy ----
def run_llm_loop(instance, current_objective=0.0, current_unassigned=None,
                 round_no=1, llm_caller=None, static_checker=None) -> Dict[str, Any]:
    loop = LLMLoop(instance, current_objective, current_unassigned or [],
                   round_no=round_no, llm_caller=llm_caller,
                   static_checker=static_checker)
    return loop.run()


if __name__ == "__main__":
    import json, sys
    sys.path.insert(0, os.path.abspath(os.path.join(BASE, "..")))
    inst = json.load(open(
        os.path.abspath(os.path.join(BASE, "..", "data", "instances",
                                     "Routes_06-08-2026_1125.json")),
        encoding="utf-8"))
    r = run_llm_loop(inst, current_objective=11.8, current_unassigned=[3, 4], round_no=1)
    print("recovery_action:", r["recovery_action"])
    print("attempts:", r["attempts_log"])
    # 验证可调用
    from solver.model import Solution
    sol = Solution([[0, 1, 2, 3, 0]], [], 10.0, True)
    import random
    removed, partial = r["destroy_fn"](sol, inst, random.Random(0))
    print("destroy_fn 可调用: removed", removed, "| partial", partial.paths)
