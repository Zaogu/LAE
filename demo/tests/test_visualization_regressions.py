"""Regression checks for actual operator attribution and truthful UI charts."""
import json
import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solver import alns
from solver.model import Solution
from ui import dashboard


def test_actual_operators_and_best_solution(monkeypatch):
    # 本测试隔离路线成本，专测算子归因及退火；完整性测试使用真实评估器。
    monkeypatch.setattr(alns, "evaluate", lambda sol, *a, **kw: {
        "objective": sol.objective, "feasible": sol.feasible})
    monkeypatch.setattr(alns, "initial_solution", lambda *a: Solution([[0, 1, 0]], [], 100, True))
    calls = {"relocate": 0, "random": 0, "greedy": 0}
    objectives = iter([91, 89])

    def relocate(sol, *a, **kw):
        calls["relocate"] += 1
        new = sol.copy()
        new.objective = 90
        return [], new

    def destroy(sol, *a, **kw):
        calls["random"] += 1
        return [], sol.copy()

    def repair(sol, *a, **kw):
        calls["greedy"] += 1
        new = sol.copy()
        new.objective = next(objectives)
        return new

    rng = random.Random(1)
    monkeypatch.setattr(rng, "random", lambda: 0.0)
    solver = alns.ALNSSolver({"instance_id": "test", "nodes": [{"id": 0}, {"id": 1}]}, rng=rng, max_iter=3, time_budget=60,
                            destroy_set={"random": destroy, "relocate": relocate},
                            repair_set={"greedy": repair}, use_checkpoint=False)
    monkeypatch.setattr(solver, "_pick", lambda ops: "random" if "random" in ops else "greedy")
    result = solver.run()
    assert calls == {"relocate": 1, "random": 2, "greedy": 2}
    assert [h["objective"] for h in result["history"]] == [100, 90, 90, 89]
    assert result["history"][1]["destroy_operator"] == "relocate"
    assert result["history"][1]["repair_operator"] is None
    assert result["history"][2]["accepted"] is True
    assert result["history"][2]["current_objective"] == 91
    assert result["objective_value"] == 89
    assert result["operator_stats"]["relocate"] == {"calls": 1, "improvements": 1, "improvement_total": 10.0}
    assert result["operator_stats"]["greedy"]["calls"] == 2
    assert result["operator_stats"]["greedy"]["improvement_total"] == 1


def test_failed_attempts_have_zero_improvement(monkeypatch):
    monkeypatch.setattr(alns, "evaluate", lambda sol, *a, **kw: {
        "objective": sol.objective, "feasible": sol.feasible})
    monkeypatch.setattr(alns, "initial_solution", lambda *a: Solution([[0, 1, 0]], [], 100, True))

    def destroy(sol, *a, **kw):
        return [], sol.copy()

    def repair(sol, *a, **kw):
        new = sol.copy()
        new.objective = 120
        return new

    result = alns.ALNSSolver({"instance_id": "test", "nodes": [{"id": 0}, {"id": 1}]}, max_iter=3, time_budget=60,
                            destroy_set={"random": destroy}, repair_set={"greedy": repair},
                            use_checkpoint=False).run()
    assert result["operator_results"]["random"] == pytest.approx(0.3)
    assert result["operator_stats"]["random"]["improvement_total"] == 0
    assert result["operator_stats"]["random"]["improvements"] == 0
    assert result["operator_stats"]["random"]["calls"] == 3


def test_missing_run_evidence_does_not_show_other_runs():
    records = [{"run_id": "old"}, {"run_id": "selected"}]
    assert dashboard._filter_evidence_for_result(records, {"run_id": "selected"}) == [records[1]]
    assert dashboard._filter_evidence_for_result(records, {"run_id": "missing"}) == []


def test_latest_ui_run_survives_new_experiment_report(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "PROJECT_ROOT", str(tmp_path))
    results = tmp_path / "experiments" / "results"
    results.mkdir(parents=True)
    ui = results / "ui_last_result.json"
    experiment = results / "A_newer.json"
    ui.write_text(json.dumps({"run_id": "selected", "instance_id": "ui"}), encoding="utf-8")
    experiment.write_text(json.dumps({"instance_id": "experiment"}), encoding="utf-8")
    os.utime(ui, (1000, 1000))
    os.utime(experiment, (2000, 2000))
    assert dashboard._load_latest_result()["instance_id"] == "ui"


def test_chart_uses_cost_improvement_not_reward_score():
    result = {
        "history": [{"iteration": i, "objective": 1052223.7161} for i in range(4)],
        "operator_results": {"shaw": 0.3},
        "operator_stats": {"shaw": {"calls": 3, "improvements": 0, "improvement_total": 0}},
    }
    fig = dashboard._view_convergence([], result)
    heatmap = next(trace for trace in fig.data if trace.type == "heatmap")
    assert list(heatmap.z[0]) == [0]
    assert list(heatmap.customdata[0][0]) == [3, 0]
    assert fig.layout.xaxis.title.text == "迭代次数"
    assert fig.layout.xaxis.dtick == 1
    assert fig.layout.yaxis.tickformat == ",.2f"
    assert heatmap.colorbar.len < 0.5


def test_old_rewards_have_an_explicit_label():
    fig = dashboard._view_convergence([], {"operator_results": {"shaw": 0.3}})
    heatmap = next(trace for trace in fig.data if trace.type == "heatmap")
    assert list(heatmap.x) == ["反馈得分"]
    assert any("旧版记录" in a.text for a in fig.layout.annotations)
