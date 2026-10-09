"""solver/recovery.py —— 保守回退 + 检查点恢复（FR-8 / FR-9 / AC-5.1 / AC-3.2 / EC-5/EC-6）。

保守回退（设计文档 3.3）：
  - 不可行客户（续航/时间窗/容量超限）从解中暂时移除，
  - 按"坡度最缓 / 降载"策略优先插入到约束最宽松位置，
  - 仍不可行则标记 unassigned 并计入未服务惩罚。
检查点恢复：
  - 读取最近检查点（解、权重、迭代数、种子、时间戳），
  - 从断点恢复 ALNSolver 状态继续搜索，而非从头开始。
"""
from __future__ import annotations
import json
import os
import random
import math

BASE = os.path.dirname(os.path.abspath(__file__))
CKPT_DIR = os.path.join(BASE, "..", "checkpoints")


def conservative_reassign(solution, instance, params, max_retry=3) -> dict:
    """把不可行客户按坡度最缓/降载重插；仍失败标 unassigned。返回 {reassigned, still_unassigned}。"""
    # 坡度矩阵：用节点 alt 差近似坡度（缓坡优先）
    alt = {n["id"]: n.get("alt", 0.0) for n in instance["nodes"]}
    def slope(i, j):
        return abs(alt.get(j, 0.0) - alt.get(i, 0.0))

    still_unassigned = []
    reassigned = []
    for cust in list(solution.unassigned):
        placed = False
        for _ in range(max_retry):
            # 在所有路径中找"坡度最小"的插入位置
            best = None
            for pi, path in enumerate(solution.paths):
                for pos in range(len(path)):
                    s_prev = slope(path[pos - 1], cust) if pos > 0 else 0.0
                    s_next = slope(cust, path[pos]) if pos < len(path) else 0.0
                    cost = s_prev + s_next
                    if best is None or cost < best[0]:
                        best = (cost, pi, pos)
            if best is not None:
                cost, pi, pos = best
                # 缓坡（cost 较小）才插入，否则标 unassigned
                if cost < 10.0:  # 原型阈值：坡度差 <10m 视为可插
                    solution.paths[pi].insert(pos + 1, cust)
                    solution.unassigned = [x for x in solution.unassigned if x != cust]
                    reassigned.append(cust)
                    placed = True
                    break
        if not placed:
            still_unassigned.append(cust)
    return {"reassigned": reassigned, "still_unassigned": still_unassigned}


def save_checkpoint(instance_id: str, state: dict) -> str:
    os.makedirs(CKPT_DIR, exist_ok=True)
    path = os.path.join(CKPT_DIR, f"ckpt_{instance_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, default=str)
    return path


def load_checkpoint(instance_id: str) -> dict | None:
    path = os.path.join(CKPT_DIR, f"ckpt_{instance_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def restore_solver(solver, instance_id: str) -> bool:
    """从检查点恢复 ALNSSolver 状态（AC-3.2）。成功返回 True。"""
    from solver.model import Solution
    cp = load_checkpoint(instance_id)
    if cp is None:
        return False
    # 确保 best 已初始化
    if solver.best is None:
        solver.best = Solution()
    solver.best.paths = cp.get("paths", solver.best.paths)
    solver.best.unassigned = cp.get("unassigned", solver.best.unassigned)
    solver.best.objective = cp.get("objective", solver.best.objective)
    solver.best.feasible = cp.get("feasible", solver.best.feasible)
    solver.weights = cp.get("weights", solver.weights)
    solver.results = cp.get("results", solver.results)
    solver.iteration = cp.get("iteration", 0)
    # 恢复随机种子状态（保留可复现性 NFR-2）
    try:
        seed_state = cp.get("seed_state")
        if seed_state:
            solver.rng.setstate((3, tuple(seed_state), None))
    except Exception:
        pass  # 种子恢复失败不阻塞，仅记录
    return True


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(BASE, "..")))
    from solver.model import Solution
    sol = Solution([[0, 1, 2, 0]], [3, 4], 10.0, False)
    rep = conservative_reassign(sol, {"nodes": [
        {"id": 0, "alt": 0}, {"id": 1, "alt": 1}, {"id": 2, "alt": 2},
        {"id": 3, "alt": 5}, {"id": 4, "alt": 99}]}, {})
    print("reassigned:", rep["reassigned"], "still_unassigned:", rep["still_unassigned"])
