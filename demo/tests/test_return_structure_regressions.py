"""回归测试：LLM 算子漏写 return 导致主循环崩溃。

背景（2026-10-11 实测）：
  prompt.py 修好 "import time" 白名单矛盾后，LLM 路径首次真正跑通
  （recovery_action=llm_ok）。随即暴露出新缺陷：deepseek-chat 生成的
  算子在构建完 new_paths 后忘记写 return，函数隐式返回 None，
  alns.py 主循环解包时抛：
      TypeError: cannot unpack non-iterable NoneType object
  原 static_check.py 只查签名与禁止模式，未落实 FR-6 第 4 条
  "返回结构提示"，故坏算子能通过检查并让整次求解崩溃。

本文件锁定两处修复：
  1) static_check 必须拦截"存在隐式返回 None 分支"的算子；
  2) 即便坏算子漏过检查，主循环也必须捕获并继续，而非崩溃。
"""
import json
import os
import random
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from llm.static_check import check_operator                # noqa: E402
from solver.alns import ALNSSolver                         # noqa: E402
from solver.model import load_params                       # noqa: E402

# 实测中触发崩溃的真实形态：末尾构建完 new_paths 却没有 return
MISSING_RETURN = (
    "def destroy(solution, instance, rng, **kwargs):\n"
    "    max_remove = kwargs.get('max_remove', 8)\n"
    "    partial = solution.copy()\n"
    "    removed = [c for p in partial.paths for c in p if c != 0][:max_remove]\n"
    "    new_paths = []\n"
    "    for path in partial.paths:\n"
    "        new_paths.append([0, 0])\n"
    "    partial.paths = new_paths\n"
)

VALID_OPERATOR = (
    "def destroy(solution, instance, rng, **kwargs):\n"
    "    removed = [c for p in solution.paths for c in p if c != 0][:2]\n"
    "    partial = solution.copy()\n"
    "    return removed, partial\n"
)


# ---------------- 静态检查：返回结构 ----------------
@pytest.mark.unit
@pytest.mark.p0
def test_missing_return_rejected():
    """漏 return 的算子必须被静态检查拦截（error_type=return_structure）。"""
    res = check_operator(MISSING_RETURN)
    assert res["passed"] is False
    assert res["error_type"] == "return_structure"
    assert res["return_ok"] is False


@pytest.mark.unit
@pytest.mark.p0
def test_valid_operator_still_passes():
    """合规算子不得被新增检查误杀。"""
    res = check_operator(VALID_OPERATOR)
    assert res["passed"] is True
    assert res["error_type"] is None


@pytest.mark.unit
@pytest.mark.p1
def test_nested_helper_scalar_return_allowed():
    """destroy 内嵌套辅助函数返回标量不应误报（只约束 destroy 自身）。"""
    code = (
        "def destroy(solution, instance, rng, **kwargs):\n"
        "    def demand(n):\n"
        "        return 1.0\n"
        "    demand(0)\n"
        "    return [], solution.copy()\n"
    )
    assert check_operator(code)["passed"] is True


@pytest.mark.unit
@pytest.mark.p1
def test_scalar_return_rejected():
    """destroy 直接返回标量（非二元组）应被拒绝。"""
    code = ("def destroy(s, i, rng, **kwargs):\n"
            "    return 42\n")
    res = check_operator(code)
    assert res["passed"] is False
    assert res["error_type"] == "return_structure"


@pytest.mark.unit
@pytest.mark.p1
def test_if_else_both_return_ok():
    """if/else 两分支都 return 应通过。"""
    code = (
        "def destroy(solution, instance, rng, **kwargs):\n"
        "    if len(solution.paths) > 1:\n"
        "        return [], solution.copy()\n"
        "    else:\n"
        "        return [], solution.copy()\n"
    )
    assert check_operator(code)["passed"] is True


# ---------------- 提示词必须说明数据结构形状 ----------------
@pytest.mark.unit
@pytest.mark.p0
def test_prompt_documents_nodes_is_list():
    """提示词必须明确 nodes/arcs 是 list，避免 LLM 猜成 dict 而崩溃。

    背景（2026-10-11 实测）：deepseek-chat 生成的算子把
    instance['nodes'] 当 dict 用（nodes.get(0)），而实际是 list of dict，
    运行时抛 AttributeError: 'list' object has no attribute 'get'，
    并因未被捕获而中断整次求解。根因是提示词只写了
    “instance: dict，含 nodes/arcs/energy_params”，未说明形状。
    """
    sys.path.insert(0, ROOT)
    from llm.prompt import build_destroy_prompt
    prompt = build_destroy_prompt({"instance_id": "t", "nodes": [],
                                   "arcs": []}, 0.0, [], 1)
    assert "list" in prompt
    assert ".get" in prompt          # 明确禁止 list 上调 .get
    assert "delta_h" in prompt       # arcs 字段形状也需说明


# ---------------- 主循环容错：坏算子不得崩溃 ----------------
@pytest.mark.system
@pytest.mark.p0
def test_solver_survives_type_error_operator():
    """算子内部对数据结构猜错（抛任意异常）时，求解不得崩溃。

    模拟截图中的真实崩溃：把 nodes 当 dict 调 .get()。
    """
    inst_path = os.path.join(ROOT, "data", "instances",
                             "Routes_06-08-2026_1446.json")
    if not os.path.exists(inst_path):
        pytest.skip("实例文件缺失")
    inst = json.load(open(inst_path, encoding="utf-8"))

    def bad_destroy(solution, instance, rng, **kwargs):
        return instance["nodes"].get(0)      # list 没有 .get -> AttributeError

    solver = ALNSSolver(inst, params=load_params(), seed=1, time_budget=3,
                        destroy_fn=bad_destroy, destroy_set={"llm": bad_destroy})
    out = solver.run()                       # 不得抛异常
    assert out["objective_value"] is not None
    assert getattr(solver, "invalid_operator_count", 0) > 0
    assert "AttributeError" in getattr(solver, "last_invalid_operator_error", "")
    # 坏算子应被禁用并回退到内置算子
    assert solver.custom_destroy is None
    assert solver.destroy_set, "算子池不得为空"


@pytest.mark.unit
@pytest.mark.p1
def test_builtin_operator_exception_still_propagates():
    """内置算子自身抛错必须上抛，不能被容错逻辑掩盖。"""
    inst = {"instance_id": "t", "nodes": [{"id": 0}, {"id": 1}]}

    def broken(sol, *a, **kw):
        raise RuntimeError("builtin bug")

    from solver.alns import repair_greedy
    solver = ALNSSolver(inst, params=load_params(), seed=1, time_budget=3,
                        destroy_set={"broken": broken},
                        repair_set={"greedy": repair_greedy})
    with pytest.raises(RuntimeError):
        solver.run()


@pytest.mark.system
@pytest.mark.p0
def test_solver_survives_none_returning_operator():
    """算子恒返回 None 时，求解必须完成而非抛 TypeError。"""
    inst_path = os.path.join(ROOT, "data", "instances",
                             "Routes_06-08-2026_1125.json")
    if not os.path.exists(inst_path):
        pytest.skip("实例文件缺失")
    inst = json.load(open(inst_path, encoding="utf-8"))

    def bad_destroy(solution, instance, rng, **kwargs):
        return None

    solver = ALNSSolver(inst, params=load_params(), seed=1, time_budget=3,
                        destroy_fn=bad_destroy, destroy_set={"llm": bad_destroy})
    out = solver.run()          # 不得抛异常
    assert out["objective_value"] is not None
    assert getattr(solver, "invalid_operator_count", 0) > 0
    assert "NoneType" in getattr(solver, "last_invalid_operator_error", "")
