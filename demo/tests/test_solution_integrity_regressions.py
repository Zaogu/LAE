"""Route integrity regressions: hand-written operators, no AI or external calls."""
import json
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
        "instance_id": "integrity-local",
        "nodes": [
            {"id": i, "x": -3.7 + i * 0.001, "y": 40.4, "alt": 650.0}
            for i in range(4)
        ],
        "arcs": [],
        "time_windows": {"start": 0, "end": 10000},
    }
    monkeypatch.setattr(alns, "CHECKPOINT_DIR", str(tmp_path / "checkpoints"))
    return instance, model.load_params()


@pytest.mark.parametrize(
    "paths,unassigned",
    [
        ([[1, 0, 2, 3, 0]], []),
        ([[0, 1, 2, 3]], []),
        ([[1, 2, 3]], []),
        ([[0, 1, 0, 2, 3, 0]], []),
        ([[0, 1, 2, 0]], []),
        ([[0, 1, 2, 3, 1, 0]], []),
        ([[0, 1, 2, 3, 99, 0]], []),
        ([[0, 1, 2, 3, 0]], [3]),
        ([[0, 1, 2, 0]], [0, 3]),
        ([[0, 1, 2, 0]], [3, 3]),
        ([[0, 1, 2, 0]], [99]),
        ([], []),
    ],
    ids=[
        "bad-start", "bad-end", "no-depot", "internal-depot",
        "missing-customer", "duplicate-customer", "unknown-customer",
        "assigned-and-unassigned", "unassigned-depot", "duplicate-unassigned",
        "unknown-unassigned", "empty-routes",
    ],
)
def test_invalid_routes_cannot_claim_feasibility(local_case, paths, unassigned):
    instance, params = local_case
    validation = model.validate_routes(paths, unassigned, instance, allow_unassigned=True)
    assert validation["passed"] is False
    assert validation["errors"]
    result = alns.evaluate(Solution(paths, unassigned, objective=0, feasible=True), instance, params)
    assert result["feasible"] is False
    assert math.isinf(result["objective"])
    assert result["validation_errors"]


def test_partial_solution_validity_is_distinct_from_complete_feasibility(local_case):
    instance, params = local_case
    paths, unassigned = [[0, 1, 2, 0]], [3]
    assert model.validate_routes(paths, unassigned, instance, allow_unassigned=True)["passed"] is True
    assert model.validate_routes(paths, unassigned, instance)["passed"] is False
    assert alns.evaluate(Solution(paths, unassigned), instance, params)["feasible"] is False
    complete = [[0, 1, 2, 3, 0]]
    assert model.validate_routes(complete, [], instance)["passed"] is True
    assert alns.evaluate(Solution(complete, []), instance, params)["feasible"] is True


@pytest.mark.parametrize("repair_name", ["repair_greedy", "repair_regret2"])
@pytest.mark.parametrize("customer_count", [3, 220], ids=["enumerated", "sampled"])
def test_builtin_insertions_never_cross_depot_boundary(local_case, monkeypatch, repair_name, customer_count):
    instance, params = local_case
    instance["nodes"] = [
        {"id": i, "x": -3.7 + i * 0.0001, "y": 40.4, "alt": 650.0}
        for i in range(customer_count + 1)
    ]
    partial = Solution([[0] + list(range(1, customer_count)) + [0]], [customer_count], 100, False)
    positions = []

    def score(sol, path, pos, customer, inst, cost_params):
        assert 0 <= pos < len(path) - 1, "Insertion must occur between depot endpoints"
        positions.append(pos)
        return -float(pos)  # Prefer the last legal gap, exposing any after-depot option.

    monkeypatch.setattr(alns, "_obj_with_insert", score)
    repaired = getattr(alns, repair_name)(partial, instance, random.Random(1), params=params)
    assert positions
    assert repaired.paths[0][0] == repaired.paths[0][-1] == 0
    assert model.validate_routes(repaired.paths, repaired.unassigned, instance)["passed"] is True


def _prepared_initial(instance, params, paths):
    solution = Solution(paths, [])
    ev = alns.evaluate(solution, instance, params)
    solution.objective, solution.feasible = ev["objective"], ev["feasible"]
    return solution


def test_removal_cost_keeps_other_customers_in_the_route(local_case):
    instance, params = local_case
    initial = _prepared_initial(instance, params, [[0, 1, 2, 3, 0]])
    reference = alns.evaluate(Solution([[0, 1, 3, 0]], [2]), instance, params)
    cost = alns._remove_cost(initial, instance, params, 2)
    assert math.isfinite(cost)
    assert cost == pytest.approx(reference["objective"] - initial.objective)
    assert initial.paths == [[0, 1, 2, 3, 0]]


def test_in_place_bad_destroy_does_not_pollute_current_or_best(local_case, monkeypatch):
    instance, params = local_case
    initial = _prepared_initial(instance, params, [[0, 1, 2, 3, 0]])
    original_paths = [list(path) for path in initial.paths]
    monkeypatch.setattr(alns, "initial_solution", lambda *args: initial.copy())
    inputs, repair_calls = [], []

    def destroy(sol, *args, **kwargs):
        inputs.append([list(path) for path in sol.paths])
        if len(inputs) == 1:
            sol.paths[0].pop(0)
            sol.paths[0].pop()
            sol.objective = 0.0
            sol.feasible = True
        return [], sol

    def repair(sol, *args, **kwargs):
        repair_calls.append(True)
        return sol.copy()

    solver = alns.ALNSSolver(
        instance, params=params, destroy_set={"custom": destroy},
        repair_set={"repair": repair}, max_iter=2, time_budget=10, use_checkpoint=False,
    )
    result = solver.run()
    assert inputs == [original_paths, original_paths]
    assert repair_calls == [True], "Invalid partial must not be passed to repair"
    assert result["paths"] == original_paths
    assert result["objective_value"] == initial.objective
    assert solver.current.paths == original_paths
    assert result["invalid_candidates"] == 1
    assert result["history"][1]["accepted"] is False
    assert result["history"][1]["repair_operator"] is None
    assert result["history"][1]["candidate_objective"] is None
    json.dumps(result, allow_nan=False)


def test_bad_repair_cannot_claim_zero_cost_or_damage_current(local_case, monkeypatch):
    instance, params = local_case
    initial = _prepared_initial(instance, params, [[0, 1, 2, 3, 0]])
    monkeypatch.setattr(alns, "initial_solution", lambda *args: initial.copy())

    def destroy(sol, *args, **kwargs):
        return [], sol

    def repair(sol, *args, **kwargs):
        sol.paths[0].remove(2)
        sol.objective = 0.0
        sol.feasible = True
        return sol

    solver = alns.ALNSSolver(
        instance, params=params, destroy_set={"custom": destroy},
        repair_set={"repair": repair}, max_iter=1, time_budget=10, use_checkpoint=False,
    )
    result = solver.run()
    assert result["paths"] == initial.paths
    assert solver.current.paths == initial.paths
    assert result["objective_value"] == initial.objective
    assert result["history"][1]["accepted"] is False
    assert result["invalid_candidates"] == 1


def test_valid_partial_then_repair_recomputes_real_joint_improvement(local_case, monkeypatch):
    instance, params = local_case
    initial = _prepared_initial(instance, params, [[0, 1, 3, 2, 0]])
    complete = [[0, 1, 2, 3, 0]]
    expected = alns.evaluate(Solution(complete, []), instance, params)["objective"]
    assert expected < initial.objective
    monkeypatch.setattr(alns, "initial_solution", lambda *args: initial.copy())

    def destroy(sol, *args, **kwargs):
        sol.paths[0].remove(2)
        sol.unassigned = [2]
        sol.feasible = False
        return [2], sol

    def repair(sol, *args, **kwargs):
        assert model.validate_routes(sol.paths, sol.unassigned, instance, allow_unassigned=True)["passed"]
        sol.paths = [list(path) for path in complete]
        sol.unassigned = []
        sol.objective = 0.0  # Operator-reported values must not determine acceptance.
        sol.feasible = False
        return sol

    result = alns.ALNSSolver(
        instance, params=params, destroy_set={"custom": destroy},
        repair_set={"repair": repair}, max_iter=1, time_budget=10, use_checkpoint=False,
    ).run()
    assert result["objective_value"] == expected
    assert result["paths"] == complete
    assert result["feasibility_rate"] == 1.0
    assert result["history"][1]["accepted"] is True
    for name in ("custom", "repair"):
        assert result["operator_stats"][name]["improvements"] == 1
        assert result["operator_stats"][name]["improvement_total"] == pytest.approx(initial.objective - expected)


def test_valid_annealing_move_preserves_best_until_true_improvement(local_case, monkeypatch):
    instance, params = local_case
    routes = [[0, 1, 2, 3, 0], [0, 2, 1, 3, 0], [0, 1, 3, 2, 0]]
    costs = {tuple(path): cost for path, cost in zip(routes, (100.0, 101.0, 99.0))}

    def controlled_evaluate(sol, inst, cost_params, rng=None):
        assert model.validate_routes(sol.paths, sol.unassigned, inst)["passed"] is True
        return {"objective": costs[tuple(sol.paths[0])], "feasible": True}

    monkeypatch.setattr(alns, "evaluate", controlled_evaluate)
    monkeypatch.setattr(alns, "initial_solution", lambda *args: Solution([list(routes[0])], [], 100.0, True))
    candidates = iter(routes[1:])
    repair_inputs = []

    def destroy(sol, *args, **kwargs):
        return [], sol

    def repair(sol, *args, **kwargs):
        repair_inputs.append(sol.objective)
        sol.paths = [list(next(candidates))]
        sol.objective = -1.0
        sol.feasible = False
        return sol

    rng = random.Random(1)
    monkeypatch.setattr(rng, "random", lambda: 0.0)
    result = alns.ALNSSolver(
        instance, params=params, rng=rng, destroy_set={"custom": destroy},
        repair_set={"repair": repair}, max_iter=2, time_budget=10, use_checkpoint=False,
    ).run()
    assert repair_inputs == [100.0, 101.0]
    assert [h["objective"] for h in result["history"]] == [100.0, 100.0, 99.0]
    assert result["history"][1]["current_objective"] == 101.0
    assert result["history"][1]["accepted"] is True
    assert result["objective_value"] == 99.0


def test_results_page_flags_invalid_archived_result_without_rewriting_it(local_case, tmp_path, monkeypatch):
    """已归档的不可行结果必须被标红，且不得被页面重写。

    迁移说明（2026-10-11 UI 重构）：原 dashboard.render_dashboard →
    results_page.render；完整性检查逻辑与只读语义不变。
    """
    from ui import state as ui_state
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(ui_state, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(ui_state, "RESULTS_DIR", str(tmp_path / "experiments" / "results"))
    monkeypatch.setattr(ui_state, "INST_DIR", str(tmp_path / "data" / "instances"))
    instance, _ = local_case
    instance_dir = tmp_path / "data" / "instances"
    instance_dir.mkdir(parents=True)
    (instance_dir / "integrity-local.json").write_text(json.dumps(instance), encoding="utf-8")
    result_dir = tmp_path / "experiments" / "results"
    result_dir.mkdir(parents=True)
    archived = {"run_id": "previous", "instance_id": "integrity-local", "paths": [[1, 2, 3]],
                "unassigned": [], "objective_value": 0.0}
    target = result_dir / "ui_last_result.json"
    content = json.dumps(archived, indent=2).encode("utf-8")
    target.write_bytes(content)
    app = AppTest.from_string(
        "import ui.state\nui.state.PROJECT_ROOT = " + repr(str(tmp_path)) + "\n"
        "ui.state.RESULTS_DIR = " + repr(str(result_dir)) + "\n"
        "ui.state.INST_DIR = " + repr(str(instance_dir)) + "\n"
        "from ui import results_page\nresults_page.render()"
    ).run(timeout=30)
    assert not app.exception
    assert any("未通过路线完整性检查" in error.value for error in app.error)
    assert target.read_bytes() == content
