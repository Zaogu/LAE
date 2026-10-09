"""solver/model.py —— SDVRPD 建模与能耗函数（FR-2 / D1 / AC-2.1 / AC-2.2）。

MILP 形式化（设计文档 3.1）：
  有向图 G=(V,A)，V={0}∪V'，0 为仓库。决策变量 x_ijk(卡车弧)、
  y_ij(无人机弧)、z_ijk(搭载)、u_ijk(卡车载荷)、p_ij(无人机载荷)。
  目标：min 卡车固定成本 + 卡车能耗 + 无人机能耗 + 时间窗软惩罚 + 未服务惩罚。

能耗函数（设计文档 3.1，可配置见 config/params.json）：
  卡车:  E = (alpha + beta*max(0,theta) + gamma*max(0,-theta)) * d * (1 + delta*u/Q)
  无人机: E = 巡航(水平距离/坡度) + 爬升(高度增量) + 垂直(起降) ，均受载荷影响。

本模块提供纯 Python 可调用函数与约束检查器，供 ALNS 主循环调用。
"""
from __future__ import annotations
import json
import math
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PARAMS_PATH = os.path.join(BASE, "..", "config", "params.json")


def load_params(path: str = PARAMS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---- 能耗函数 ------------------------------------------------------
def truck_energy(theta: float, d_m: float, u_kg: float, Q_kg: float,
                 p: dict) -> float:
    """卡车弧能耗。theta 弧度，d_m 水平距离米，u_kg 当前载重，Q_kg 卡车容量。

    符合公式 E=(alpha+beta*max(0,θ)+gamma*max(0,-θ))*d*(1+delta*u/Q)。
    返回值随 θ 正向增、随 u 线性放大（AC-2.1）。
    """
    ep = p["energy_params"]
    alpha, beta, gamma, delta = ep["alpha"], ep["beta"], ep["gamma"], ep["delta"]
    load_factor = 1.0 + delta * (u_kg / Q_kg if Q_kg > 0 else 0.0)
    return (alpha + beta * max(0.0, theta) + gamma * max(0.0, -theta)) * d_m * load_factor


def drone_energy(theta: float, d_m: float, delta_h_m: float, p_ij_kg: float,
                 p: dict) -> dict:
    """无人机弧三段能耗（AC-2.2）。返回 {cruise, climb, vertical, total}。

    cruise: 水平飞行能耗，随坡度附加阻力；
    climb:  爬升阶段能耗（高度增量、载荷）；
    vertical: 起降/垂直飞行能耗（与载荷直接相关）。
    """
    ep = p["energy_params"]
    base = ep["drone_base_energy_per_km"]
    load_factor = 1.0 + ep["drone_load_factor"] * (p_ij_kg / ep["drone_max_payload_kg"])
    cruise = base * (d_m / 1000.0) * (1.0 + ep["drone_cruise_slope_factor"] * abs(theta)) * load_factor
    climb = ep["drone_climb_factor"] * abs(max(0.0, delta_h_m)) * 0.01 * load_factor
    vertical = ep["drone_vertical_factor"] * 0.02 * load_factor  # 起降固定小量，与载荷相关
    return {"cruise": round(cruise, 4), "climb": round(climb, 4),
            "vertical": round(vertical, 4), "total": round(cruise + climb + vertical, 4)}


def drone_feasible(energy_wh: float, p: dict) -> bool:
    """续航可行性边界：能耗 ≤ η·Bmax（设计文档 3.1 时间窗与续航约束）。"""
    ep = p["energy_params"]
    return energy_wh <= ep["drone_safety_margin"] * ep["drone_battery_capacity_wh"]


# ---- 约束检查器 ----------------------------------------------------
def check_capacity(load_kg: float, capacity_kg: float) -> bool:
    return load_kg <= capacity_kg + 1e-9


class Solution:
    """ALNS 解的轻量表示。

    paths: list of 子路径（每个子路径为节点 id 序列，含仓库 0 起终点）。
    unassigned: 未服务客户集合。
    """

    def __init__(self, paths=None, unassigned=None, objective=0.0, feasible=True):
        self.paths = paths if paths is not None else []
        self.unassigned = unassigned if unassigned is not None else []
        self.objective = objective
        self.feasible = feasible

    def copy(self):
        s = Solution([list(p) for p in self.paths], list(self.unassigned),
                     self.objective, self.feasible)
        return s

    def to_dict(self):
        return {"paths": self.paths, "unassigned": self.unassigned,
                "objective": self.objective, "feasible": self.feasible}
