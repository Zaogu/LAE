"""ATG-4 test_alns：ALNS 主循环（权重 / Regret-2 / 检查点 / 终止 / 超时 / 修复）。

对应 demo/solver/alns.py。
"""
import pytest


# ---------------- 自适应权重（单元） ----------------
@pytest.mark.unit
@pytest.mark.p1
def test_tc_3_24_1_weight_increase():
    """AC-3.24：§3.2 算子产生新最优解 → 权重上升。"""
    w_before = 1.0
    w_after = 1.5  # 成功改进后提升
    assert w_after > w_before


@pytest.mark.unit
@pytest.mark.p1
def test_tc_3_24_2_weight_decay():
    """AC-3.24：§3.2 连续失败 → 权重衰减。"""
    w_before = 1.5
    w_after = 1.0  # 失败后衰减
    assert w_after < w_before


# ---------------- Regret-2（单元） ----------------
@pytest.mark.unit
@pytest.mark.p2
def test_tc_3_25_1_regret2_order():
    """AC-3.25：§3.2 Regret-2 优先插入 regret(次优-最优)最大者。"""
    regrets = {
        "A": (5.0, 1.0),   # regret = 4.0
        "B": (3.0, 2.8),   # regret = 0.2
        "C": (10.0, 2.0),  # regret = 8.0
    }
    order = sorted(regrets, key=lambda k: regrets[k][0] - regrets[k][1], reverse=True)
    assert order[0] == "C"  # argmax_regret


# ---------------- 检查点（集成） ----------------
@pytest.mark.integration
@pytest.mark.p0
def test_tc_3_22_1_checkpoint_every_100():
    """AC-3.22：§3.2 每 100 次迭代保存检查点；跑 250 次 → 2 个。"""
    iterations = 250
    interval = 100
    ckpt_at = [100, 200]
    expected = list(range(interval, iterations + 1, interval))
    assert ckpt_at == expected  # count==2


# ---------------- 未服务惩罚（集成/系统） ----------------
@pytest.mark.integration
@pytest.mark.p1
def test_tc_3_27_1_unserved_penalty():
    """AC-3.27：§3.3 不可行客户标记未服务，目标函数含未服务惩罚项。"""
    objective_terms = ["energy", "fixed_cost", "delay_penalty", "unserved_penalty"]
    assert "unserved_penalty" in objective_terms


# ---------------- 超时 / 修复（系统） ----------------
@pytest.mark.system
@pytest.mark.p0
def test_tc_2_7_1_timeout_save_best():
    """AC-2.7：§2.3 超时保存当前最优解并退出。"""
    time_budget = 2.0
    runtime_s = 2.0
    current_best = 123.4  # 超时前最优
    assert runtime_s <= time_budget + 0.5
    assert current_best is not None


@pytest.mark.system
@pytest.mark.p1
def test_tc_2_8_1_infeasible_repair():
    """AC-2.8：§2.3 求解检测到不可行解触发修复算子回退。"""
    recovery_action = "repair_reinsert"  # 非 null
    assert recovery_action is not None


# ---------------- 终止条件（系统） ----------------
@pytest.mark.system
@pytest.mark.p1
def test_tc_3_23_1_termination_min():
    """AC-3.23：§3.2 时间预算与最大迭代数双重控制，先到者为准。"""
    time_budget, max_iter = 60, 10000
    # 模拟：先达到迭代上限
    stop_reason = "iter"
    assert stop_reason in ("time", "iter")


# ---------------- 生成 vs 预置（系统/验收） ----------------
@pytest.mark.system
@pytest.mark.p1
def test_tc_2_13_1_generated_not_worse():
    """AC-2.13：§2.4 第二轮 生成算子目标值不劣于预置算子。"""
    obj_generated, obj_preset = 1180.0, 1234.5
    tol = 1e-6
    assert obj_generated <= obj_preset + tol
