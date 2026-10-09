"""experiments/anomaly.py —— 异常注入实验（设计文档 3.4 消融三 / FR-13）。

在**异常注入**条件下量化容错机制贡献（H3 平台价值验证）：

| 注入场景 | 操作 | 测试目标 |
|---|---|---|
| 语法错误注入 | LLM 生成代码中插入语法错误 | 静态检查 + 重试能否捕获恢复 |
| 接口不匹配注入 | 函数签名改为不兼容格式 | 接口约束检查能否拦截触发重试 |
| 超时注入 | 时间预算压缩到 10% | 检查点恢复能否从断点继续 |

每种场景各运行 N 次（默认 10），统计"有无容错"下：
  - 完成率（闭环不中断的比例）
  - 恢复次数（recovery_action 触发的次数）
  - 恢复后解质量（objective 差异）

输出：experiments/results/anomaly_{scenario}_{ft}.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import glob

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from solver.alns import ALNSSolver, PREDEFINED_DESTROY, PREDEFINED_REPAIR
from solver.model import load_params
from llm.closed_loop import LLMLoop
from llm.generate import load_llm_config, compile_operator, predefined_fallback_destroy
from llm.static_check import check_operator
from llm.prompt import build_destroy_prompt

RESULTS_DIR = os.path.join(PROJECT_ROOT, "experiments", "results")


def _load_instance(instance_id: str) -> dict:
    for fp in glob.glob(os.path.join(PROJECT_ROOT, "data", "instances", "*.json")):
        inst = json.load(open(fp, encoding="utf-8"))
        if inst["instance_id"] == instance_id:
            return inst
    raise FileNotFoundError(instance_id)


# ---------- 场景 1：语法错误注入 ----------
def inject_syntax_error() -> str:
    """强制 LLM 生成含语法错误的破坏算子（模拟 LLM 不稳定输出）。"""
    return "def destroy(solution, instance, rng, **kwargs):\n    bad syntax here !!!\n    return [], solution\n"


def run_scenario_syntax(instance: dict, n: int, time_budget: float,
                        fault_tolerance: bool = True) -> dict:
    """语法错误注入：有容错应经重试回退预置算子、闭环不中断。"""
    results = {"completed": 0, "total": n, "recoveries": 0, "objectives": []}
    bad_code = inject_syntax_error()

    for i in range(n):
        try:
            cfg = {"enabled": True, "api_key": "test", "base_url": "http://test",
                    "model": "m", "temperature": 0.2, "max_tokens": 500, "timeout": 10}
            # 模拟 LLM 总返回坏码
            def fake_llm(prompt, cfg2):
                return {"status": "ok", "code": bad_code, "raw": bad_code, "error": ""}

            if fault_tolerance:
                # 有容错：走闭环（静态检查拦截 + 重试 + 回退）
                loop = LLMLoop(instance, 0.0, [], round_no=1, llm_caller=fake_llm)
                res = loop.run()
                fn = res["destroy_fn"]
                if res["recovery_action"] in ("predefined_fallback", "llm_error_fallback"):
                    results["recoveries"] += 1
            else:
                # 无容错：直接编译坏码 -> 失败
                fn, err = compile_operator(bad_code)
                if fn is None:
                    results["objectives"].append(None)
                    continue

            solver = ALNSSolver(instance, params=load_params(), seed=100 + i,
                                 time_budget=time_budget,
                                 destroy_fn=fn if fault_tolerance else PREDEFINED_DESTROY.get("random"),
                                 use_checkpoint=fault_tolerance)
            out = solver.run()
            results["completed"] += 1
            results["objectives"].append(out["objective_value"])
        except Exception:
            results["objectives"].append(None)

    results["completion_rate"] = results["completed"] / n
    valid = [v for v in results["objectives"] if v is not None]
    results["mean_obj"] = (sum(valid) / len(valid)) if valid else None
    return results


# ---------- 场景 2：接口不匹配注入 ----------
def inject_bad_signature() -> str:
    """强制返回签名不符的算子（缺少 rng 参数）。"""
    return "def destroy(solution, instance, **kwargs):\n    return [], solution\n"


def run_scenario_signature(instance: dict, n: int, time_budget: float,
                           fault_tolerance: bool = True) -> dict:
    results = {"completed": 0, "total": n, "recoveries": 0, "objectives": []}
    bad_code = inject_bad_signature()

    for i in range(n):
        try:
            chk = check_operator(bad_code)
            if fault_tolerance and not chk["passed"]:
                # 有容错：拦截，回退预置
                fn, _ = compile_operator(predefined_fallback_destroy())
                results["recoveries"] += 1
            else:
                # 无容错：签名不符算子被调用 -> 运行时失败
                fn, err = compile_operator(bad_code)
                if fn is None:
                    results["objectives"].append(None)
                    continue
            solver = ALNSSolver(instance, params=load_params(), seed=200 + i,
                                 time_budget=time_budget,
                                 destroy_fn=fn,
                                 use_checkpoint=fault_tolerance)
            out = solver.run()
            results["completed"] += 1
            results["objectives"].append(out["objective_value"])
        except Exception:
            results["objectives"].append(None)

    results["completion_rate"] = results["completed"] / n
    valid = [v for v in results["objectives"] if v is not None]
    results["mean_obj"] = (sum(valid) / len(valid)) if valid else None
    return results


# ---------- 场景 3：超时注入 ----------
def run_scenario_timeout(instance: dict, n: int, normal_budget: float,
                         fault_tolerance: bool = True) -> dict:
    """超时注入：时间预算压缩到 10%，有容错应保存检查点并可恢复。"""
    results = {"completed": 0, "total": n, "recoveries": 0, "objectives": []}
    short_budget = normal_budget * 0.1

    for i in range(n):
        try:
            # 第一阶段：短预算（模拟超时）
            s1 = ALNSSolver(instance, params=load_params(), seed=300 + i,
                             time_budget=short_budget,
                             use_checkpoint=fault_tolerance,
                             destroy_set=dict(PREDEFINED_DESTROY),
                             repair_set=dict(PREDEFINED_REPAIR))
            out1 = s1.run()
            if fault_tolerance:
                # 检查点已保存，恢复后继续（模拟断点续跑）
                from solver.recovery import restore_solver
                s2 = ALNSSolver(instance, params=load_params(), seed=300 + i,
                                 time_budget=short_budget,
                                 use_checkpoint=True,
                                 destroy_set=dict(PREDEFINED_DESTROY),
                                 repair_set=dict(PREDEFINED_REPAIR))
                if restore_solver(s2, instance["instance_id"]):
                    out2 = s2.run()
                    out1["objective_value"] = out2["objective_value"]
                    results["recoveries"] += 1
            results["completed"] += 1
            results["objectives"].append(out1["objective_value"])
        except Exception:
            results["objectives"].append(None)

    results["completion_rate"] = results["completed"] / n
    valid = [v for v in results["objectives"] if v is not None]
    results["mean_obj"] = (sum(valid) / len(valid)) if valid else None
    return results


SCENARIOS = {
    "syntax_error": run_scenario_syntax,
    "bad_signature": run_scenario_signature,
    "timeout_10pct": run_scenario_timeout,
}


def main():
    ap = argparse.ArgumentParser(description="SDVRPD 异常注入实验")
    ap.add_argument("--instance", default="Routes_06-08-2026_1125")
    ap.add_argument("--n", type=int, default=10, help="每场景运行次数（默认 10）")
    ap.add_argument("--time-budget", type=float, default=10.0)
    ap.add_argument("--scenario", choices=list(SCENARIOS.keys()) + ["all"], default="all")
    args = ap.parse_args()

    inst = _load_instance(args.instance)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    scenarios = [s for s in SCENARIOS if args.scenario == "all" or s == args.scenario]

    for sc in scenarios:
        fn = SCENARIOS[sc]
        for ft in (True, False):
            tag = "with_ft" if ft else "no_ft"
            if sc == "timeout_10pct":
                rep = fn(inst, args.n, args.time_budget, fault_tolerance=ft)
            else:
                rep = fn(inst, args.n, args.time_budget, fault_tolerance=ft)
            p = os.path.join(RESULTS_DIR, f"anomaly_{sc}_{tag}_{inst['instance_id']}.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(rep, f, ensure_ascii=False, indent=2, default=str)
            print(f"[{sc}/{tag}] completion={rep['completion_rate']:.2f} "
                  f"recoveries={rep['recoveries']} mean_obj={rep['mean_obj']}")


if __name__ == "__main__":
    main()
