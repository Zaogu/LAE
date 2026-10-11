"""scripts/run_sdvrpd_once.py —— 单次 SDVRPD 求解 + 结果与证据落盘。

用途：以固定 seed/预算跑一个真实实例，把求解结果写入
runs/run_<run_id>.json，并按 AC-6.1 证据字段写入 evidence/rounds/<run_id>/。

用法：
    python -m scripts.run_sdvrpd_once --instance data/instances/Routes_06-08-2026_1125.json \
        --seed 1 --time-budget 10 --run-id run_manual_001
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from solver.alns import ALNSSolver                       # noqa: E402
from solver.model import load_params                     # noqa: E402
from verify.evidence import new_record, append_round, prompt_hash  # noqa: E402

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RUNS_DIR = os.path.join(BASE, "runs")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default=os.path.join(
        "data", "instances", "Routes_06-08-2026_1125.json"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--time-budget", type=float, default=10.0)
    ap.add_argument("--max-iter", type=int, default=10000)
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args()

    inst_path = args.instance if os.path.isabs(args.instance) \
        else os.path.join(BASE, args.instance)
    with open(inst_path, "r", encoding="utf-8") as f:
        inst = json.load(f)

    params = load_params()
    solver = ALNSSolver(inst, params=params, seed=args.seed,
                        time_budget=args.time_budget, max_iter=args.max_iter)
    t0 = time.time()
    out = solver.run()
    wall_ms = int((time.time() - t0) * 1000)

    run_id = args.run_id or f"run_{time.strftime('%Y%m%d_%H%M%S')}"
    record = {
        "run_id": run_id,
        "instance_id": out["instance_id"],
        "instance_file": os.path.relpath(inst_path, BASE).replace("\\", "/"),
        "node_count": len(inst.get("nodes", [])),
        "seed": args.seed,
        "time_budget_s": args.time_budget,
        "objective_value": out["objective_value"],
        "initial_objective": out["initial_objective"],
        "feasibility_rate": out["feasibility_rate"],
        "improvement_rate": (
            round((out["initial_objective"] - out["objective_value"])
                  / out["initial_objective"], 6)
            if out["initial_objective"] else None),
        "iterations": out["iterations"],
        "runtime_ms": out["runtime_ms"],
        "wall_ms": wall_ms,
        "startup_ms": out["startup_ms"],
        "timed_out": out["timed_out"],
        "timeout_reason": out["timeout_reason"],
        "unassigned": out["unassigned"],
        "route_validation": out["route_validation"],
        "paths": out["paths"],
        "operator_stats": out["operator_stats"],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    os.makedirs(RUNS_DIR, exist_ok=True)
    run_path = os.path.join(RUNS_DIR, f"{run_id}.json")
    with open(run_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    ev = new_record(
        iteration_id=0,
        stage="alns_execution",
        llm_prompt_hash=prompt_hash(json.dumps({
            "instance_id": out["instance_id"], "seed": args.seed,
            "budget": args.time_budget}, ensure_ascii=False)),
        generated_code="",
        execution={
            "status": "completed" if not out["timed_out"] else "timed_out",
            "objective_value": out["objective_value"],
            "feasibility_rate": out["feasibility_rate"],
            "runtime_ms": out["runtime_ms"],
        },
        recovery_action=None,
    )
    ev["run_id"] = run_id
    ev["instance_id"] = out["instance_id"]
    ev_path = append_round(run_id, ev)

    print(json.dumps({
        "run_id": run_id,
        "instance_id": out["instance_id"],
        "objective_value": out["objective_value"],
        "initial_objective": out["initial_objective"],
        "feasibility_rate": out["feasibility_rate"],
        "iterations": out["iterations"],
        "runtime_ms": out["runtime_ms"],
        "timed_out": out["timed_out"],
        "run_path": os.path.relpath(run_path, BASE).replace("\\", "/"),
        "evidence_path": os.path.relpath(ev_path, BASE).replace("\\", "/") if ev_path else None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
