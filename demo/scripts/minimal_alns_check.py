"""Minimal ALNS reproducibility check used by LAE\\run_system.ps1.

Usage:
    python scripts/minimal_alns_check.py <time_budget_seconds>
"""
import glob
import json
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from solver.alns import ALNSSolver
from solver.model import load_params


def main() -> None:
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    inst_files = sorted(glob.glob(os.path.join(PROJECT_ROOT, "data", "instances", "*.json")))
    if not inst_files:
        raise SystemExit("No instance JSON found. Run: python data/instance.py --force")
    with open(inst_files[0], encoding="utf-8") as f:
        inst = json.load(f)
    params = load_params()
    out1 = ALNSSolver(inst, params=params, seed=1, time_budget=budget).run()
    out2 = ALNSSolver(inst, params=params, seed=1, time_budget=budget).run()
    if abs(out1["objective_value"] - out2["objective_value"]) >= 1e-6:
        raise SystemExit("Fixed-seed reproducibility check failed.")
    print("instance_id:", inst["instance_id"])
    print("objective:", out1["objective_value"])
    print("feasibility_rate:", out1["feasibility_rate"])
    print("runtime_ms:", out1["runtime_ms"])
    print("iterations:", out1["iterations"])


if __name__ == "__main__":
    main()
