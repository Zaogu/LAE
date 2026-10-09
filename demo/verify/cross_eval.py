"""verify/cross_eval.py —— 跨模型评估器（FR-20 / AC-7.2）。

设计文档 3.4 实验二"跨模型评估"核心逻辑：
  能耗函数不同，各自算出的目标值必然不同，这不能证明坡度建模的实质影响。
  真正能证明的是——用不同能耗模型求解出的路径，在"真实评估器"下的实际执行
  成本差异。

本模块提供：
  - 三种能耗模型（简化/线性/耦合）各自求解路径；
  - 固定"真实评估器"（坡度-载荷耦合完整模型）统一评估三种解的实际成本；
  - 输出成本对比表（判断坡度建模是否必要）。

三模型定义：
  M1 恒定能耗：  成本 = α × 总水平距离（忽略坡度/载荷）
  M2 距离-载荷线性： 成本 = (α + δ·u/Q) × 总水平距离（含载荷，不含坡度）
  M3 坡度-载荷耦合：  成本 = (α+β·θ⁺+γ·θ⁻)·d·(1+δ·u/Q)（完整 SDVRPD，真实评估器）

跨模型评估 = 用 M3（耦合模型）作为固定评估器，计算 M1/M2/M3 各自求解
路径的实际执行成本，对比差异。
"""
from __future__ import annotations
import json
import math
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from solver.model import load_params, truck_energy  # type: ignore


def _node_map(instance: dict) -> dict:
    return {n["id"]: n for n in instance["nodes"]}


def _seg_geometry(instance: dict, i: int, j: int, node_map: dict):
    """返回段 (i,j) 的水平距离(米)、高度差(米)、坡度(弧度)。"""
    for a in instance.get("arcs", []):
        if a["i"] == i and a["j"] == j:
            return a["d"], a["delta_h"], a["theta"]
    ni, nj = node_map.get(i), node_map.get(j)
    if ni is None or nj is None:
        return 0.0, 0.0, 0.0
    d_km = math.dist((ni["x"], ni["y"]), (nj["x"], nj["y"]))
    d_m = d_km * 1000.0
    dh = nj.get("alt", 0.0) - ni.get("alt", 0.0)
    th = math.atan2(dh, d_m) if d_m > 1e-6 else 0.0
    return d_m, dh, th


def solve_with_model(instance: dict, model_id: str, params: dict,
                     seed: int = 1, time_budget: float = 15.0) -> dict:
    """用指定能耗模型求解路径（ALNS），返回解（paths + 该模型自评估目标值）。

    三种模型通过不同 params 变体驱动 ALNS 目标评估：
      M1: 置 β=γ=δ=0 → 恒定能耗
      M2: 置 β=γ=0（保留 δ）→ 距离-载荷线性
      M3: 完整（默认 params）→ 坡度-载荷耦合
    """
    from solver.alns import ALNSSolver
    p2 = json.loads(json.dumps(params))  # 深拷贝
    ep = p2["energy_params"]
    if model_id == "M1_const":
        ep["beta"] = 0.0; ep["gamma"] = 0.0; ep["delta"] = 0.0
    elif model_id == "M2_linear":
        ep["beta"] = 0.0; ep["gamma"] = 0.0
        # 保留 delta（载荷线性）
    # M3_coupled: 不动（默认耦合）
    # max_iter 随 time_budget 缩放：2000 节点下评估慢，小预算配小迭代，避免总耗时过长
    max_iter = max(50, int(time_budget * 8))
    from solver.alns import PREDEFINED_DESTROY, PREDEFINED_REPAIR
    solver = ALNSSolver(instance, params=p2, seed=seed,
                         time_budget=time_budget, max_iter=max_iter,
                         destroy_set=dict(PREDEFINED_DESTROY),  # 含 relocate（方案 2）
                         repair_set=dict(PREDEFINED_REPAIR),
                         use_checkpoint=False)
    out = solver.run()
    return {"model": model_id, "paths": out["paths"],
            "self_objective": out["objective_value"],
            "feasible": out["feasibility_rate"]}


def _eval_with_model(instance: dict, paths: list, params: dict,
                     model_id: str) -> float:
    """固定评估器：用指定模型的成本函数，对给定路径计算实际执行成本。

    这就是跨模型评估的核心——同一路径，在不同"真实成本"假设下的执行成本。
    """
    p = params
    ep = p["energy_params"]
    Q = ep.get("truck_capacity_kg", 100.0)
    node_map = _node_map(instance)
    total = 0.0
    for path in paths:
        load = len([i for i in path if i != 0]) * 5.0  # 每客户 5kg
        for idx in range(len(path) - 1):
            i, j = path[idx], path[idx + 1]
            d_m, dh, th = _seg_geometry(instance, i, j, node_map)
            if model_id == "M1_const":
                # 恒定：只按距离
                seg = ep["alpha"] * d_m
            elif model_id == "M2_linear":
                # 距离-载荷线性（不含坡度）
                seg = (ep["alpha"] + ep["delta"] * (load / Q)) * d_m
            else:
                # M3 完整耦合（真实评估器）
                seg = truck_energy(th, d_m, load, Q, p)
            total += seg
            load = max(0.0, load - 5.0)
    return round(total, 4)


def cross_model_eval(instance: dict, params: dict = None,
                     seed: int = 1, time_budget: float = 15.0) -> dict:
    """执行跨模型评估（设计文档 3.4 实验二流程）。

    1. 用 M1/M2/M3 分别求解同一实例路径；
    2. 统一输入"真实评估器"（M3 耦合模型），计算各解实际执行成本；
    3. 对比差异，判断坡度建模是否必要。

    time_budget 可调：12 实例批量评估时适当压缩，避免总耗时过长。
    """
    params = params or load_params()
    models = ["M1_const", "M2_linear", "M3_coupled"]
    solutions = {m: solve_with_model(instance, m, params, seed=seed,
                                     time_budget=time_budget)
                 for m in models}

    # 固定真实评估器 = M3（坡度-载荷耦合完整模型）
    real_cost = {m: _eval_with_model(instance, solutions[m]["paths"], params, "M3_coupled")
                 for m in models}

    # 判断标准（设计文档 3.4）：若简化模型解在真实评估下成本显著更高，
    # 则证明坡度建模必要。
    m1_real, m3_real = real_cost["M1_const"], real_cost["M3_coupled"]
    gap = (m1_real - m3_real) / m3_real if m3_real else 0.0

    return {
        "instance_id": instance.get("instance_id"),
        "solutions": solutions,
        "real_cost_by_model": real_cost,
        "gap_M1_vs_M3": round(gap, 4),
        "slope_modeling_necessary": gap > 0.02,  # 阈值：简化模型成本高 2% 即认为必要
        "note": "真实评估器=M3 耦合模型；gap>0.02 表示坡度-载荷耦合建模有实质影响",
    }


if __name__ == "__main__":
    import argparse
    import glob
    ap = argparse.ArgumentParser(description="SDVRPD 跨模型评估")
    ap.add_argument("--time-budget", type=float, default=10.0,
                    help="单模型 ALNS 时间预算（秒）；12 实例批量时适当压缩")
    ap.add_argument("--instance", default=None, help="指定实例 ID；默认取第一个")
    args = ap.parse_args()
    inst_path = glob.glob(os.path.join(PROJECT_ROOT, "data", "instances", "*.json"))
    if not inst_path:
        print("无实例，请先运行 data/instance.py --force")
        sys.exit(0)
    if args.instance:
        inst_path = [p for p in inst_path if args.instance in p]
        if not inst_path:
            print(f"未找到实例 {args.instance}")
            sys.exit(1)
    inst = json.load(open(inst_path[0], encoding="utf-8"))
    rep = cross_model_eval(inst, time_budget=args.time_budget)
    print(json.dumps({
        "instance": rep["instance_id"],
        "real_cost_by_model": rep["real_cost_by_model"],
        "gap_M1_vs_M3": rep["gap_M1_vs_M3"],
        "slope_modeling_necessary": rep["slope_modeling_necessary"],
    }, ensure_ascii=False, indent=2))
