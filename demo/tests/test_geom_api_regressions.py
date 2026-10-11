"""回归测试：LLM 算子的受控几何查询接口 slope()/distance_m()。

背景（2026-10-11）：
  instance['arcs'] 只含“航点顺序弧”（0→1→2…，见 data/instance.py 第 125-132 行），
  不是完整邻接表。提示词原让 LLM 用 arcs 查路径相邻节点的坡度，但 ALNS 搜索时
  路径相邻节点（如 1985→1980）在 arcs 里命中率仅 0.3%，导致 LLM 算子的坡度评分
  退化为随机，93 次调用零改进。

  修复：在 solver.model 提供 slope()/distance_m()，按真实经纬度/高度实时计算任意
  两节点的坡度/距离，并由 compile_operator 注入到 LLM 算子的命名空间。
"""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from solver.model import slope, distance_m, load_params        # noqa: E402
from solver.alns import get_eval_ctx                           # noqa: E402
from llm.generate import compile_operator                       # noqa: E402

INST_PATH = os.path.join(ROOT, "data", "instances",
                         "Routes_06-08-2026_1125.json")


@pytest.fixture(scope="module")
def inst():
    if not os.path.exists(INST_PATH):
        pytest.skip("实例文件缺失")
    return json.load(open(INST_PATH, encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.p0
def test_slope_matches_eval_ctx(inst):
    """slope() 必须与主求解器 get_eval_ctx 的 theta 矩阵一致。"""
    ctx = get_eval_ctx(inst, load_params())
    nmap = ctx["nmap"]
    for a, b in [(1985, 1980), (0, 1), (0, 2), (10, 20), (15, 37), (100, 999)]:
        ia, ib = nmap[a], nmap[b]
        ref = float(ctx["theta"][ia, ib])
        assert abs(slope(inst, a, b) - ref) < 1e-6


@pytest.mark.unit
@pytest.mark.p0
def test_distance_m_matches_eval_ctx(inst):
    """distance_m() 必须与 get_eval_ctx 的距离矩阵一致。"""
    ctx = get_eval_ctx(inst, load_params())
    nmap = ctx["nmap"]
    for a, b in [(10, 20), (15, 37), (100, 999)]:
        ia, ib = nmap[a], nmap[b]
        ref = float(ctx["dist"][ia, ib]) * 1000.0
        assert abs(distance_m(inst, a, b) - ref) < 1e-3


@pytest.mark.unit
@pytest.mark.p0
def test_slope_d0_but_dh_nonzero(inst):
    """经纬度相同、仅高度不同的节点：slope 应为 ±π/2，而非 0。

    这是数据里大量存在的情形（前几行节点 x/y 完全相同、alt 不同）。
    修复前 slope 用了 d>1e-6 阈值，错误地返回 0。
    """
    # 节点 0 和 1 坐标相同、高度差 0.6m
    assert abs(slope(inst, 0, 1)) - 1.5707963 < 1e-4


@pytest.mark.unit
@pytest.mark.p0
def test_compile_injects_geometry_functions(inst):
    """compile_operator 必须把 slope/distance_m 注入到算子命名空间。"""
    code = (
        "def destroy(solution, instance, rng, **kwargs):\n"
        "    served = [c for p in solution.paths for c in p if c != 0]\n"
        "    k = min(kwargs.get('max_remove', 8), len(served))\n"
        "    removed = rng.sample(served, k)\n"
        "    _ = slope(instance, 0, 1)\n"
        "    _ = distance_m(instance, 0, 1)\n"
        "    partial = solution.copy()\n"
        "    partial.paths = [[x for x in p if x not in set(removed)] for p in partial.paths]\n"
        "    partial.unassigned = list(partial.unassigned) + removed\n"
        "    return removed, partial\n"
    )
    fn, err = compile_operator(code)
    assert fn is not None, err

    from solver.alns import initial_solution
    import random
    sol = initial_solution(inst, random.Random(1), load_params())
    rem, partial = fn(sol, inst, random.Random(2), max_remove=3)
    assert len(rem) == 3
    assert partial.paths


@pytest.mark.unit
@pytest.mark.p0
def test_unknown_node_returns_zero(inst):
    """未知节点应返回 0.0（容错友好），不抛异常。"""
    assert slope(inst, 999999, 0) == 0.0
    assert distance_m(inst, 999999, 0) == 0.0
