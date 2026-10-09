"""verify/metrics.py —— 评估指标计算（FR-11 / AC-7.1 关联）。

指标（设计文档 3.4）：
  - objective_gap: (f_alg - f_best)/f_best
  - feasibility_rate: 可行解数/总运行数
  - runtime_ms
  - improvement_rate: (f_initial - f_final)/f_initial
自研，纯 Python，无额外依赖。
"""
from __future__ import annotations


def objective_gap(f_alg: float, f_best: float) -> float:
    if f_best in (0, None):
        return 0.0
    return (f_alg - f_best) / f_best


def improvement_rate(f_initial: float, f_final: float) -> float:
    if f_initial in (0, None):
        return 0.0
    return (f_initial - f_final) / f_initial


def feasibility_rate(feasible_count: int, total_runs: int) -> float:
    if total_runs <= 0:
        return 0.0
    return feasible_count / total_runs


def summarize_run(objective_value: float, feasibility_rate: float,
                  runtime_ms: int, initial_objective: float,
                  best_known: float = None) -> dict:
    out = {
        "objective_value": objective_value,
        "feasibility_rate": feasibility_rate,
        "runtime_ms": runtime_ms,
        "improvement_rate": improvement_rate(initial_objective, objective_value),
    }
    if best_known is not None:
        out["objective_gap"] = objective_gap(objective_value, best_known)
    return out


if __name__ == "__main__":
    print(summarize_run(100.0, 1.0, 5000, initial_objective=120.0, best_known=90.0))
