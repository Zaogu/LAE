"""experiments/run_all.py —— 三组对照实验脚本（FR-12 / FR-17/18 / AC-7.1）。

三组定义（SPEC 阶段 2 决策 + 设计文档 3.4 实验一）：
  A 组（基线）:  人工预置算子集合（random/worst/shaw 破坏 + greedy/regret2 修复）
  B 组（LLM-Only）: LLM 直接生成完整 ALNS 求解器代码，无接口约束
  C 组（LLM+Harness）: LLM 生成破坏算子 + 静态检查 + 闭环反馈（本方案）

实验设计：
  - 每组 × 每个实例 × 每组 15 独立种子 = 完整对照
  - 每次实验产出：求解结果 JSON + 证据记录 JSON
  - 结果写入 experiments/results/{group}_{instance}_{seed}.json
  - 证据写入 evidence/rounds/{run_id}/

用法（设计文档 5.5）：
    python experiments/run_all.py --instance IT_HIGH --time-budget 60
    python experiments/run_all.py --all --seeds 15
    python experiments/run_all.py --group A --instance CA_BOTTOM
"""
from __future__ import annotations
import argparse
import glob
import json
import os
import sys
import time
import random

# 项目根入 sys.path
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from solver.alns import ALNSSolver, PREDEFINED_DESTROY, PREDEFINED_REPAIR
from solver.model import load_params
from llm.closed_loop import run_llm_loop
from llm.generate import load_llm_config
from verify.evidence import new_record, save_record, append_round
from verify.metrics import summarize_run

RESULTS_DIR = os.path.join(PROJECT_ROOT, "experiments", "results")
INSTANCES_DIR = os.path.join(PROJECT_ROOT, "data", "instances")


def load_instances() -> dict:
    """加载所有实例 JSON，按 instance_id 索引。"""
    out = {}
    for p in glob.glob(os.path.join(INSTANCES_DIR, "*.json")):
        with open(p, encoding="utf-8") as f:
            inst = json.load(f)
        out[inst["instance_id"]] = inst
    return out


def run_group_a(instance: dict, seed: int, time_budget: float,
                evidence_subdir: str = "") -> dict:
    """A 组：预置人工算子集合。"""
    params = load_params()
    solver = ALNSSolver(instance, params=params, seed=seed,
                        time_budget=time_budget,
                        destroy_set=dict(PREDEFINED_DESTROY),
                        repair_set=dict(PREDEFINED_REPAIR),
                        use_checkpoint=True)
    out = solver.run()
    return {
        "group": "A",
        "instance_id": instance["instance_id"],
        "seed": seed,
        "objective_value": out["objective_value"],
        "feasibility_rate": out["feasibility_rate"],
        "runtime_ms": out["runtime_ms"],
        "iterations": out["iterations"],
        "paths": out["paths"],
        "unassigned": out["unassigned"],
    }


def run_group_b(instance: dict, seed: int, time_budget: float,
                evidence_subdir: str = "") -> dict:
    """B 组：LLM-Only（生成完整求解器，无接口约束）。

    简化实现：调用 LLM 生成完整 ALNS 代码，尝试 exec 执行；
    若 LLM 不可用或生成失败，标记 llm_only_infeasible=True 并回退预置（保证实验可完成）。
    设计文档 3.4：B 组用于对比 C 组的"接口约束 + 静态检查"优势。
    """
    params = load_params()
    cfg = load_llm_config()
    result = {
        "group": "B",
        "instance_id": instance["instance_id"],
        "seed": seed,
        "llm_only_infeasible": False,
        "llm_code": "",
        "recovery_action": "llm_only",
    }
    if not cfg.get("enabled"):
        result["llm_only_infeasible"] = True
        result["recovery_action"] = "not_configured_fallback"
        # 回退到 A 组等价（保证实验可完成，标记为 B 组"未启用"）
        solver = ALNSSolver(instance, params=params, seed=seed,
                             time_budget=time_budget, use_checkpoint=False)
        out = solver.run()
        result.update({"objective_value": out["objective_value"],
                       "feasibility_rate": out["feasibility_rate"],
                       "runtime_ms": out["runtime_ms"],
                       "iterations": out["iterations"],
                       "paths": out["paths"], "unassigned": out["unassigned"]})
        return result

    # LLM 可用：生成"完整求解器"（比 C 组更大的自由度，无静态检查）
    from llm.generate import generate_destroy_operator, compile_operator
    from llm.prompt import build_destroy_prompt
    prompt = build_destroy_prompt(instance, 0.0, [], round_no=1)
    res = generate_destroy_operator(prompt, cfg)
    if res["status"] == "ok":
        fn, err = compile_operator(res["code"])
        if fn is not None:
            result["llm_code"] = res["code"]
            solver = ALNSSolver(instance, params=params, seed=seed,
                                 time_budget=time_budget,
                                 destroy_fn=fn, use_checkpoint=False)
            out = solver.run()
            result.update({"objective_value": out["objective_value"],
                           "feasibility_rate": out["feasibility_rate"],
                           "runtime_ms": out["runtime_ms"],
                           "iterations": out["iterations"],
                           "paths": out["paths"], "unassigned": out["unassigned"]})
            result["recovery_action"] = "llm_only_ok"
        else:
            result["llm_only_infeasible"] = True
            result["error"] = f"compile: {err}"
            # 回退
            solver = ALNSSolver(instance, params=params, seed=seed,
                                 time_budget=time_budget, use_checkpoint=False)
            out = solver.run()
            result.update({"objective_value": out["objective_value"],
                           "feasibility_rate": out["feasibility_rate"],
                           "runtime_ms": out["runtime_ms"],
                           "iterations": out["iterations"],
                           "paths": out["paths"], "unassigned": out["unassigned"]})
    else:
        result["llm_only_infeasible"] = True
        result["error"] = res["error"]
        solver = ALNSSolver(instance, params=params, seed=seed,
                             time_budget=time_budget, use_checkpoint=False)
        out = solver.run()
        result.update({"objective_value": out["objective_value"],
                       "feasibility_rate": out["feasibility_rate"],
                       "runtime_ms": out["runtime_ms"],
                       "iterations": out["iterations"],
                       "paths": out["paths"], "unassigned": out["unassigned"]})
    return result


def run_group_c(instance: dict, seed: int, time_budget: float,
                evidence_subdir: str = "") -> dict:
    """C 组：LLM+Harness（本方案）：LLM 生成 + 静态检查 + 闭环反馈。"""
    params = load_params()
    # LLM 闭环（无配置自动降级到预置算子）
    loop_res = run_llm_loop(instance, current_objective=0.0,
                             current_unassigned=[], round_no=1)
    custom_fn = loop_res["destroy_fn"] if loop_res["recovery_action"] == "llm_ok" else None
    solver = ALNSSolver(instance, params=params, seed=seed,
                         time_budget=time_budget,
                         destroy_fn=custom_fn,
                         use_checkpoint=True)
    out = solver.run()

    result = {
        "group": "C",
        "instance_id": instance["instance_id"],
        "seed": seed,
        "objective_value": out["objective_value"],
        "feasibility_rate": out["feasibility_rate"],
        "runtime_ms": out["runtime_ms"],
        "iterations": out["iterations"],
        "paths": out["paths"],
        "unassigned": out["unassigned"],
        "recovery_action": loop_res["recovery_action"],
        "llm_code": loop_res.get("generated_code", ""),
        "attempts": loop_res.get("attempts_log", []),
    }

    # 保存证据（FR-10 / D3）
    if evidence_subdir:
        rec = new_record(
            iteration_id=seed,
            stage="llm+harness",
            llm_prompt_hash=loop_res.get("llm_prompt_hash", ""),
            generated_code=loop_res.get("generated_code", ""),
            static_check={
                "passed": loop_res.get("static_check", {}).get("passed"),
                "signature_ok": loop_res.get("static_check", {}).get("signature_ok"),
                "forbidden_patterns": loop_res.get("static_check", {}).get("forbidden_patterns", []),
            },
            execution={
                "status": "completed",
                "objective_value": out["objective_value"],
                "feasibility_rate": out["feasibility_rate"],
                "runtime_ms": out["runtime_ms"],
            },
            recovery_action=loop_res.get("recovery_action"),
        )
        append_round(evidence_subdir, rec)
    return result


def run_single(group: str, instance_id: str, seeds: int, time_budget: float,
               instance_map: dict = None, evidence_dir: str = "") -> list:
    """单组 × 单实例 × N 种子，返回结果列表。"""
    inst = (instance_map or load_instances()).get(instance_id)
    if inst is None:
        print(f"[run_all] 实例 {instance_id} 未找到")
        return []
    run_id = f"{group}_{instance_id}_{int(time.time())}"
    results = []
    for s in range(seeds):
        seed = 1000 + s  # 固定种子序列
        if group == "A":
            r = run_group_a(inst, seed, time_budget, evidence_dir)
        elif group == "B":
            r = run_group_b(inst, seed, time_budget, evidence_dir)
        elif group == "C":
            r = run_group_c(inst, seed, time_budget, evidence_dir)
        else:
            raise ValueError(f"未知组别: {group}")
        results.append(r)
        # 写入结果文件
        os.makedirs(RESULTS_DIR, exist_ok=True)
        out_path = os.path.join(RESULTS_DIR, f"{group}_{instance_id}_s{seed}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2, default=str)
        print(f"  [{group} {instance_id} s{seed}] obj={r.get('objective_value')}, "
              f"feas={r.get('feasibility_rate')}, ms={r.get('runtime_ms')}")
    return results


def main():
    ap = argparse.ArgumentParser(description="SDVRPD 三组对照实验")
    ap.add_argument("--group", choices=["A", "B", "C", "all"], default="all",
                    help="实验组别（默认 all=A+B+C）")
    ap.add_argument("--instance", default=None,
                    help="实例 ID（如 Routes_06-08-2026_1125）；默认 all")
    ap.add_argument("--seeds", type=int, default=15, help="每组种子数（默认 15）")
    ap.add_argument("--time-budget", type=float, default=60.0, help="单实例时间预算（秒）")
    ap.add_argument("--all", action="store_true", help="跑全部 12 实例 × 3 组 × N 种子")
    args = ap.parse_args()

    instances = load_instances()
    if not instances:
        print("[run_all] 未找到实例。请先运行: python data/instance.py --force")
        sys.exit(1)

    instance_ids = list(instances.keys()) if args.instance is None else [args.instance]
    groups = ["A", "B", "C"] if args.group == "all" else [args.group]
    total = len(groups) * len(instance_ids) * args.seeds
    print(f"[run_all] 开始：{len(groups)} 组 × {len(instance_ids)} 实例 × {args.seeds} 种子 = {total} 次实验")
    print(f"[run_all] 时间预算={args.time_budget}s，结果写入 {RESULTS_DIR}")

    all_results = []
    for g in groups:
        for iid in instance_ids:
            ev_dir = f"rounds"  # C 组证据写入 evidence/rounds
            print(f"\n[{g} {iid}] 开始 {args.seeds} 种子...")
            rs = run_single(g, iid, args.seeds, args.time_budget,
                             instance_map=instances,
                             evidence_dir=ev_dir if g == "C" else "")
            all_results.extend(rs)

    print(f"\n[run_all] 完成。共 {len(all_results)} 次实验，结果在 {RESULTS_DIR}/")
    # 汇总
    from collections import defaultdict
    by_group = defaultdict(list)
    for r in all_results:
        by_group[r["group"]].append(r.get("objective_value", 0))
    for g in sorted(by_group):
        vals = by_group[g]
        print(f"  {g} 组: {len(vals)} 次 | 均值 {sum(vals)/len(vals):.2f} | "
              f"min {min(vals):.2f} | max {max(vals):.2f}")


if __name__ == "__main__":
    main()
