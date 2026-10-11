"""Search regressions using real objective evaluation, no external model calls."""
import copy
import random
import time
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from solver import alns
from solver.model import Solution, load_params, validate_routes


@pytest.fixture
def case():
    instance = {'instance_id': 'search-regression', 'nodes': [
        {'id': i, 'x': -3.7 + (i % 4) * .002, 'y': 40.4 + (i // 4) * .001,
         'alt': 650 + i * 3} for i in range(15)], 'arcs': [],
        'time_windows': {'end': 10}}
    params = copy.deepcopy(load_params())
    params['time_window']['phi_per_hour'] = 100
    return instance, params


def evaluated(paths, unassigned, instance, params):
    sol = Solution(paths, unassigned)
    ev = alns.evaluate(sol, instance, params)
    sol.objective, sol.feasible = ev['objective'], ev['feasible']
    return sol


@pytest.mark.parametrize('tail', [[9, 10, 11, 12, 13], [12, 9, 13, 11, 10]])
@pytest.mark.parametrize('position', [0, 5, 13])
def test_insertion_matches_full_evaluation_after_same_prefix(case, tail, position):
    inst, params = case
    alns._INC_CACHE.clear()
    first = [0] + list(range(1, 14)) + [0]
    alns._path_prefix(first, alns.get_eval_ctx(inst, params), params)
    path = [0] + list(range(1, 9)) + tail + [0]
    sol = evaluated([path], [14], inst, params)
    predicted = alns._obj_with_insert(sol, path, position, 14, inst, params)
    inserted = sol.copy()
    inserted.paths[0].insert(position + 1, 14)
    inserted.unassigned.remove(14)
    assert predicted == pytest.approx(alns.evaluate(inserted, inst, params)['objective'], abs=.0002)


def test_prefix_cache_separates_energy_context_and_is_bounded(case):
    inst, params = case
    alns._INC_CACHE.clear()
    path = [0] + list(range(1, 15)) + [0]
    one = alns._path_prefix(path, alns.get_eval_ctx(inst, params), params)
    other_params = copy.deepcopy(params)
    other_params['energy_params']['alpha'] *= 2
    two = alns._path_prefix(path, alns.get_eval_ctx(inst, other_params), other_params)
    assert two[1][-1] > one[1][-1]
    rng = random.Random(2)
    for _ in range(70):
        route = list(range(1, 15))
        rng.shuffle(route)
        alns._path_prefix([0] + route + [0], alns.get_eval_ctx(inst, params), params)
    assert len(alns._INC_CACHE) <= alns._INC_CACHE_MAX


def test_large_route_sampling_keeps_original_and_nearest_gaps(case):
    inst, params = case
    inst = copy.deepcopy(inst)
    inst['nodes'] = [{'id': i, 'x': -3.7 + i*.0001, 'y': 40.4, 'alt': 650}
                     for i in range(301)]
    path = [0] + list(range(1, 300)) + [0]
    positions = alns._candidate_positions(path, 300, inst, params, random.Random(1),
                                           max_cands=16, anchor=(0, 123, 124))
    assert {0, len(path)-2, 123, 298}.issubset(positions)
    assert len(positions) <= 16
    assert all(0 <= p < len(path)-1 for p in positions)


def test_worst_removal_selects_largest_saving(case, monkeypatch):
    inst, params = case
    sol = evaluated([[0]+list(range(1,15))+[0]], [], inst, params)
    costs = {i: alns._remove_cost(sol, inst, params, i) for i in range(1,15)}
    monkeypatch.setattr(alns, '_remove_cost', lambda s, ins, p, customer: costs[customer])
    removed, partial = alns.destroy_worst(sol, inst, random.Random(1), params=params, k=1)
    assert removed == [min(costs, key=costs.get)]
    assert validate_routes(partial.paths, partial.unassigned, inst, allow_unassigned=True)['passed']


def test_regret_uses_its_scored_option_without_resampling(case, monkeypatch):
    inst, params = case
    sol = evaluated([[0]+list(range(1,14))+[0]], [14], inst, params)
    calls = []
    real_options = alns._insertion_options
    def options(*args, **kwargs):
        calls.append(1)
        assert len(calls) == 1
        return real_options(*args, **kwargs)
    monkeypatch.setattr(alns, '_insertion_options', options)
    out = alns.repair_regret2(sol, inst, random.Random(4), params=params)
    assert out.feasible
    assert calls == [1]


def test_cooling_and_acceptance_reduce_drift(case):
    inst, params = case
    solver = alns.ALNSSolver(inst, params=params, use_checkpoint=False)
    solver.initial_objective = 1000
    solver.current = Solution([[0,1,0]], [], objective=1000, feasible=True)
    now = time.perf_counter()
    hot = solver._temperature(now, now+100)
    cold = solver._temperature(now-99, now+1)
    assert 0 < cold < hot / 50
    assert solver._accept_candidate(999, 0)
    assert not solver._accept_candidate(1001, 0)
    assert not solver._accept_candidate(2000, cold)


def test_stagnation_recovery_preserves_best_and_route_integrity(case):
    inst, params = case
    solver = alns.ALNSSolver(inst, params=params, seed=1, use_checkpoint=False,
        destroy_set={'noop': lambda sol, ins, rng, **kw: ([], sol)},
        max_iter=6, time_budget=2, stagnation_limit=2)
    out = solver.run()
    assert out['search_restarts'] == 3
    assert out['objective_value'] == out['initial_objective']
    assert out['route_validation']['passed']
    assert sum(h.get('restarted', False) for h in out['history']) == 3
