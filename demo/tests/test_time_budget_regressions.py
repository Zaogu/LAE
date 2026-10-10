"""Time-budget regressions; no network or generated AI code is used."""
import math
import random
import sys
from pathlib import Path

import pytest

DEMO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO_ROOT))

from solver import alns, model
from solver.model import Solution


@pytest.fixture
def local_case(tmp_path, monkeypatch):
    instance = {
        "instance_id": "time-local",
        "nodes": [{"id": i, "x": -3.7 + i * 0.001, "y": 40.4, "alt": 650.0}
                   for i in range(4)],
        "arcs": [], "time_windows": {"start": 0, "end": 10000},
    }
    monkeypatch.setattr(alns, "CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    return instance, model.load_params()


def test_cooperative_operator_stops_at_deadline_and_keeps_best(local_case, monkeypatch):
    instance, params = local_case
    initial = Solution([[0, 1, 2, 3, 0]], [], 100.0, True)
    monkeypatch.setattr(alns, "initial_solution", lambda *args: initial.copy())
    monkeypatch.setattr(alns, "evaluate", lambda sol, *args, **kwargs:
                        {"objective": sol.objective, "feasible": sol.feasible,
                         "validation_errors": []})

    def never_finishes(sol, instance, rng, **kwargs):
        while True:
            alns.check_deadline()

    solver = alns.ALNSSolver(
        instance, params=params, seed=1, time_budget=0.03,
        time_safety_margin=0, destroy_set={"slow": never_finishes},
        repair_set={"repair": lambda sol, *args, **kwargs: sol},
        use_checkpoint=False,
    )
    result = solver.run()
    assert result["timed_out"] is True
    assert result["timeout_reason"]
    assert result["objective_value"] == 100.0
    assert result["paths"] == initial.paths
    assert result["history"] == [{
        "iteration": 0, "objective": 100.0,
        "current_objective": 100.0, "elapsed_ms": result["history"][0]["elapsed_ms"]
    }]
    assert result["budget_overrun_ms"] <= 100


def test_llm_removal_is_capped_before_expensive_repair(local_case, monkeypatch):
    instance, params = local_case
    initial = Solution([[0, 1, 2, 3, 0]], [], 100.0, True)
    monkeypatch.setattr(alns, "initial_solution", lambda *args: initial.copy())
    monkeypatch.setattr(alns, "evaluate", lambda sol, *args, **kwargs:
                        {"objective": sol.objective, "feasible": sol.feasible,
                         "validation_errors": []})
    observed = []

    def llm_destroy(sol, instance, rng, **kwargs):
        # Deliberately ignores max_remove: the harness must still cap it.
        return [1, 2, 3], sol.copy()

    def repair(sol, *args, **kwargs):
        observed.append(len(sol.unassigned))
        out = sol.copy()
        out.unassigned = []
        return out

    solver = alns.ALNSSolver(
        instance, params=params, seed=1, time_budget=0.2,
        max_custom_removed=2, destroy_fn=llm_destroy,
        destroy_set={"preset": lambda sol, *args, **kwargs: ([], sol.copy())},
        repair_set={"repair": repair}, use_checkpoint=False,
    )
    monkeypatch.setattr(solver, "_pick", lambda ops: "llm" if "llm" in ops else "repair")
    result = solver.run()
    assert observed and max(observed) <= 2
    assert result["route_validation"]["passed"] is True
    assert math.isfinite(result["objective_value"])
