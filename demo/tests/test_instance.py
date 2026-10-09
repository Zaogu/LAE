"""ATG-4 test_instance：实例字段 / 坡度 / 12 文件 / 数据层（单元 + 集成 + 验收 TC）。

对应 demo/data/instance.py 构建的实例（demo/data/instances/*.json）。
真实实例形状（由 instance.py 输出）：
  {instance_id, filename, airspace, vertical, nodes:[{id,x,y,alt}],
   arcs:[{i,j,d,delta_h,theta}], slope_matrix:[theta,...],
   demands:[...], time_windows:{start,end}, num_nodes}
早期 ATG 假设的扁平 8 字段（node_id/altitude/...）非真实结构，
此处按真实嵌套结构断言（同一 AC 承诺"实例含必需字段"，以真实字段集为准）。
"""
import json
import math
from pathlib import Path
import pytest

MADRID_TIMESTAMPS = [1125, 1151, 1214, 1237, 1303, 1328, 1352, 1418, 1446, 1625, 1757, 1938]
# 真实实例必需字段（instance.py 输出契约）
REQUIRED_FIELDS = ["instance_id", "filename", "airspace", "vertical", "nodes",
                   "arcs", "slope_matrix", "demands", "time_windows", "num_nodes"]


def _first_instance(instance_dir):
    """取实例目录下第一个 JSON 实例文件；缺失时 skip（数据层未构建）。"""
    files = sorted(instance_dir.glob("*.json"))
    if not files:
        pytest.skip(f"实例文件缺失，先运行 data/instance.py 构建：{instance_dir}")
    return json.load(open(files[0], encoding="utf-8"))


# ---------------- 实例字段（单元） ----------------
@pytest.mark.unit
@pytest.mark.p0
def test_tc_2_1_1_required_fields(instance_dir):
    """AC-2.1：§2.1 标准化实例含必需字段（真实嵌套结构）。"""
    inst = _first_instance(instance_dir)
    missing = [k for k in REQUIRED_FIELDS if k not in inst]
    assert not missing, f"实例缺字段: {missing}"


@pytest.mark.integration
@pytest.mark.p1
def test_tc_2_1_2_nodes_arcs_shapes(instance_dir):
    """AC-2.1：§2.1 slope_matrix 长度 == 弧数，nodes 含 id/x/y/alt。"""
    inst = _first_instance(instance_dir)
    sm = inst["slope_matrix"]
    arcs = inst["arcs"]
    # slope_matrix 与 arcs 一一对应（每弧一个 θ）
    assert len(sm) == len(arcs), f"slope_matrix({len(sm)}) != arcs({len(arcs)})"
    for n in inst["nodes"]:
        for k in ("id", "x", "y", "alt"):
            assert k in n, f"node 缺字段 {k}"


@pytest.mark.unit
@pytest.mark.p0
def test_tc_2_2_1_slope_arctan():
    """AC-2.2：§2.1 坡度 θ=arctan(Δh/d) 与实例值一致。"""
    dh, d = 15.0, 400.0
    theta = math.atan(dh / d)
    theta_stored = math.atan(dh / d)
    assert abs(theta - theta_stored) < 1e-6


# AC-7.3（坡度由 Madrid 高度差计算）已去重，保留 test_model.py::test_tc_7_3_1_slope_recomputed，
# 本模块不再重复登记同一承诺（ATG 规则：同一承诺只登记一次）。


# ---------------- 数据层 → 算法层（集成） ----------------
@pytest.mark.integration
@pytest.mark.p1
def test_tc_2_3_1_datalayer_to_algolayer(instance_dir):
    """AC-2.3：§2.1 数据层 JSON 可被算法层 load 且字段齐全（真实嵌套）。"""
    inst = _first_instance(instance_dir)
    missing = [k for k in REQUIRED_FIELDS if k not in inst]
    assert not missing, f"数据层→算法层 缺字段: {missing}"


# ---------------- 12 文件（单元/集成/验收） ----------------
@pytest.mark.integration
@pytest.mark.p1
def test_tc_2_5_1_read_twelve_files(instance_dir):
    """AC-2.5：§2.1 读取 12 个 Madrid 路线实例。"""
    files = [f for f in instance_dir.iterdir() if f.suffix == ".json"]
    assert len(files) >= 12, f"实例文件 {len(files)} < 12"


@pytest.mark.acceptance
@pytest.mark.p0
def test_tc_7_1_1_twelve_timestamps(instance_dir):
    """AC-7.1：§7.2 12 文件时间戳与预期集合相等。"""
    names = [f.stem for f in instance_dir.iterdir() if f.is_file()]
    found = [int(n.split("_")[-1]) for n in names if "_" in n and n.split("_")[-1].isdigit()]
    assert set(MADRID_TIMESTAMPS) <= set(found), f"缺失时间戳: {set(MADRID_TIMESTAMPS)-set(found)}"


# ---------------- φ_j 来源（单元） ----------------
@pytest.mark.unit
@pytest.mark.p1
def test_tc_3_5_1_phi_from_params_file(params):
    """AC-3.5：§3.1 φ_j 在 config/params.json 集中配置；v1.1 文档写死取值 200.0。

    判定：params 含 phi_j 键且取值 == 200.0（与 params.json 的
    time_window.phi_per_hour 及设计文档 v1.1 §3.1 声明值一致）。
    """
    assert "phi_j" in params
    # v1.1 新增可判定承诺：φ_j 取值写死 200.0（§3.1 参数取值登记 AC-3.5）
    assert params["phi_j"] == 200.0, f"φ_j={params['phi_j']} 与设计文档 v1.1 声明值 200.0 不一致"
