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
from ui import state as ui_state
from ui import charts


def test_actual_operators_and_best_solution(monkeypatch):
    """算子归因与退火：relocate 由轮盘赌选中（不再被每 3 轮强制）。

    历史变更（2026-10-11）：原实现用 `iteration % 3 == 0` 硬编码强制
    每第 3 轮执行 relocate 并跳过 repair；实测该规则在 2000 节点实例上
    调用 93 次、改进 0 次，纯粹消耗预算。relocate 已改为择优插入并
    参与自适应权重，由收益决定使用频率。本测试改为显式交替选择
    relocate 与 random，验证两种路径的归因仍然正确。
    """
    # 本测试隔离路线成本，专测算子归因及退火；完整性测试使用真实评估器。
    monkeypatch.setattr(alns, "evaluate", lambda sol, *a, **kw: {
        "objective": sol.objective, "feasible": sol.feasible})
    monkeypatch.setattr(alns, "initial_solution", lambda *a: Solution([[0, 1, 0], [0, 2, 0]], [], 100, True))
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
    solver = alns.ALNSSolver({"instance_id": "test", "nodes": [{"id": 0}, {"id": 1}, {"id": 2}]}, rng=rng, max_iter=3, time_budget=60,
                            destroy_set={"random": destroy, "relocate": relocate},
                            repair_set={"greedy": repair}, use_checkpoint=False)
    # 显式按轮次交替：第 1 轮 relocate（跳过 repair），第 2/3 轮 random+repair
    # _pick 每轮调用两次（选破坏算子、选修复算子）。
    # 第 1 轮选 relocate（返回完整解，不再选修复算子），
    # 第 2/3 轮选 random 破坏 + greedy 修复，与旧测试语义一致。
    destroy_picks = iter(["relocate", "random", "random"])

    def _pick(ops):
        if "relocate" in ops:                     # 正在选破坏算子
            return next(destroy_picks, "random")
        return "greedy" if "greedy" in ops else list(ops)[0]

    monkeypatch.setattr(solver, "_pick", _pick)
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


def test_missing_run_evidence_does_not_show_other_runs(tmp_path, monkeypatch):
    """证据按 run_id 过滤：只保留当前运行，其它运行不得混入。

    迁移说明（2026-10-11 UI 重构）：原 dashboard._filter_evidence_for_result
    改为 state.load_evidence(run_id=...) 在加载时过滤，语义不变。
    """
    monkeypatch.setattr(ui_state, "EVIDENCE_DIR", str(tmp_path))
    rounds = tmp_path / "rounds" / "sel"
    rounds.mkdir(parents=True)
    (tmp_path / "iter_1.json").write_text(json.dumps({"run_id": "old"}), encoding="utf-8")
    (rounds / "iter_1.json").write_text(
        json.dumps({"run_id": "selected", "iteration_id": 1}), encoding="utf-8")
    assert [r["run_id"] for r in ui_state.load_evidence("selected")] == ["selected"]
    assert ui_state.load_evidence("missing") == []


def test_latest_ui_run_survives_new_experiment_report(tmp_path, monkeypatch):
    """ui_last_result.json 指针优先于更新的实验文件。

    迁移说明：原 dashboard._load_latest_result → state.load_last_result。
    """
    monkeypatch.setattr(ui_state, "RESULTS_DIR", str(tmp_path))
    ui = tmp_path / "ui_last_result.json"
    experiment = tmp_path / "A_newer.json"
    ui.write_text(json.dumps({"run_id": "selected", "instance_id": "ui"}), encoding="utf-8")
    experiment.write_text(json.dumps({"instance_id": "experiment"}), encoding="utf-8")
    os.utime(ui, (1000, 1000))
    os.utime(experiment, (2000, 2000))
    assert ui_state.load_last_result()["instance_id"] == "ui"


def test_chart_uses_cost_improvement_not_reward_score():
    """算子条形图用真实改进量（improvement_total），而非旧版反馈得分。"""
    result = {
        "history": [{"iteration": i, "objective": 1052223.7161} for i in range(4)],
        "operator_results": {"shaw": 0.3},
        "operator_stats": {"shaw": {"calls": 3, "improvements": 0, "improvement_total": 0}},
    }
    conv = charts.convergence(result["history"])
    assert conv.layout.xaxis.title.text == "迭代次数"
    bars = charts.operator_bars(result)
    bar = next(t for t in bars.data if t.type == "bar")
    assert list(bar.x) == [0]
    assert list(bar.customdata[0]) == [3, 0]
    assert bars.layout.xaxis.title.text == "目标值降低量（元）"


def test_old_rewards_surface_a_distinct_chart():
    """只有旧版 operator_results、无 operator_stats 时，图表明确走空状态。"""
    bars = charts.operator_bars({"operator_results": {"shaw": 0.3}})
    assert not [t for t in bars.data if t.type == "bar"]
    assert any("没有算子贡献记录" in (a.text or "") for a in bars.layout.annotations)
