"""llm/prompt.py —— LLM 提示词组织（FR-5 / 设计文档 3.2 提示词设计）。

采用"分析-思想-代码"三步结构（设计文档 3.2）：
  1) 分析 SDVRPD 的坡度-载荷-能耗耦合特征 + 当前解瓶颈；
  2) 用自然语言阐述破坏算子的启发式逻辑；
  3) 输出符合预定接口的可执行 Python 函数。

提示词中嵌入当前实例的特征摘要（坡度分布、载荷状态、目标函数值）与
当前解状态，使 LLM 生成"实例感知"的破坏算子（创新点四）。
"""
from __future__ import annotations
import json

# 破坏算子的固定接口签名（SPEC 数据模型 / 静态检查目标）
DESTROY_SIGNATURE = "def destroy(solution, instance, rng, **kwargs)"


def instance_features(instance: dict) -> dict:
    """提取实例特征摘要：坡度分布、节点数、机型、时间窗（设计文档 3.2 实例感知）。"""
    th = [a.get("theta", 0.0) for a in instance.get("arcs", [])]
    th = [t for t in th if t is not None]
    if th:
        max_th = max(abs(t) for t in th)
        mean_th = sum(abs(t) for t in th) / len(th)
    else:
        max_th = mean_th = 0.0
    return {
        "instance_id": instance.get("instance_id"),
        "airspace": instance.get("airspace"),
        "vertical": instance.get("vertical"),
        "num_nodes": instance.get("num_nodes"),
        "num_drones": instance.get("num_drones"),
        "drone_types": instance.get("drone_types", []),
        "slope_max_deg": round(max_th * 57.2958, 3),
        "slope_mean_deg": round(mean_th * 57.2958, 3),
        "time_window": instance.get("time_windows"),
    }


def build_destroy_prompt(instance: dict, current_objective: float,
                         current_unassigned: list, round_no: int = 1,
                         last_error: str = "") -> str:
    """构造破坏算子生成提示词。last_error 用于失败重试时拼回（FR-7）。"""
    feat = instance_features(instance)
    parts = [
        f"你是组合优化专家，请为坡度依赖的卡车-无人机协同配送问题（SDVRPD）设计一个"
        f"ALNS 破坏算子（destroy operator）。",
        "",
        f"【实例特征】(第 {round_no} 轮生成)",
        f"  空域配置: {feat['airspace']} / 垂直可用性: {feat['vertical']}",
        f"  节点数: {feat['num_nodes']}，可用无人机数: {feat['num_drones']}，机型: {feat['drone_types']}",
        f"  坡度范围: 最大 {feat['slope_max_deg']:.2f}°，均值 {feat['slope_mean_deg']:.2f}°",
        f"  软时间窗: {feat['time_window']}",
        "",
        f"【当前解状态】",
        f"  当前目标函数值: {current_objective}",
        f"  当前未服务客户数: {len(current_unassigned)}",
    ]
    if last_error:
        parts += [
            "",
            f"【上一轮生成失败原因（请避免重复）】",
            last_error,
        ]
    parts += [
        "",
        "【任务】",
        "1. 分析：结合坡度-载荷耦合特征，指出现有破坏策略的瓶颈（如陡坡路段载重放大能耗）。",
        "2. 思想：用自然语言说明你的破坏启发式逻辑（例如'优先移除位于陡坡路段且当前"
        "载重较高的客户'）。",
        "3. 代码：输出【一个】可执行的 Python 函数，必须严格满足以下签名与约束：",
        f"   签名: {DESTROY_SIGNATURE}",
        "   - solution: 对象，属性 .paths(list[list[int]]) 与 .unassigned(list[int])",
        "   - 每条路径必须保持 [0, 客户编号..., 0]，0 是仓库，不是客户，禁止移除或加入 unassigned",
        "   - 使用 solution.copy() 创建部分解，禁止原地修改输入；每个客户在 paths 和 unassigned 中合计恰好出现一次",
        "   - 移除客户只改变客户分配，必须保留其他客户及仓库起终点，不能删除包含其他客户的整条路径",
        "   - instance: dict，含 nodes/arcs/energy_params；可读 instance['arcs'] 获取坡度",
        "   - rng: 标准库 random.Random 实例",
        "   - 返回: (removed: list[int], partial: solution)，partial 为移除后的解",
        "",
        "【严格约束】",
        "  - 只能 import 标准库（math/random），禁止文件/网络 I/O，禁止 import os/sys/subprocess",
        "  - 函数体必须是有限循环，无递归无限",
        "  - 不要写注释外的额外语句；只输出：一段自然语言分析 + 代码",
        "  - 代码放在 ```python ... ``` 代码块内，便于解析",
    ]
    return "\n".join(parts)
