"""ATG-4 conftest：fixtures 绑定 ATG-3 数据（真实 Madrid 实例 / 合成常量 / 参数 / 临时证据目录）。

所有 test_*.py 通过下列 fixture 取数，保证可复现（固定常量与 seed=1）。
"""
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]  # demo/


# ---------- 参数与实例 ----------
@pytest.fixture(scope="session")
def params():
    """归一化参数：将 demo/config/params.json 的嵌套结构映射为测试约定的扁平键。

    真实 params.json 按 §5.6 以嵌套分组（energy_params/time_window/cost_params），
    而 ATG 测试按 AC 约定引用扁平键 phi_j/eta/B_max/delta。此归一化层保证：
    测试与真实配置对齐，且未来 params.json 结构调整只改本处一处。
    缺失键抛带提示的 KeyError（运行期暴露，非静默）。
    """
    raw = json.load(open(ROOT / "config" / "params.json", encoding="utf-8"))
    ep = raw.get("energy_params", {})
    tw = raw.get("time_window", {})
    cp = raw.get("cost_params", {})
    norm = {
        "phi_j": tw.get("phi_per_hour"),
        "eta": ep.get("drone_safety_margin"),
        "B_max": ep.get("drone_battery_capacity_wh"),
        "delta": ep.get("delta"),
        "alpha": ep.get("alpha"),
        "beta": ep.get("beta"),
        "gamma": ep.get("gamma"),
        "unassigned_penalty": cp.get("unassigned_penalty"),
        "num_trucks": raw.get("network", {}).get("num_trucks"),
    }
    missing = [k for k, v in norm.items() if v is None]
    if missing:
        raise KeyError(f"params.json 归一化缺失键 {missing}，请检查 config/params.json 结构")
    return norm


@pytest.fixture(scope="session")
def instance_dir():
    """demo/data/instances：12 个 Madrid 路线文件目录（AC-7.1）。

    真实目录为 data/instances（由 data/instance.py 构建输出），
    非早期假设的 data/madrid。
    """
    return ROOT / "data" / "instances"


@pytest.fixture(scope="session")
def evidence_dir():
    """demo/evidence：证据记录与检查点（AC-2.4/3.29）。"""
    return ROOT / "evidence"


@pytest.fixture(scope="session")
def zenodo_dir():
    """对照基准数据（AC-3.33/7.2）。

    真实基准为 Zenodo 21403496 的 merged_all.csv，位于仓库
    docs/运行与验证数据/data/21403496/（非早期假设的 demo/data/zenodo/）。
    缺失时返回 None，测试标 BLOCKED 而非失败。
    """
    d = ROOT.parent / "docs" / "运行与验证数据" / "data" / "21403496"
    return d if d.exists() else None


@pytest.fixture(scope="session")
def zenodo_csv(zenodo_dir):
    """基准 CSV 路径（AC-3.33/7.2 量级对照的真实数据源）。

    返回 demo/../docs/运行与验证数据/data/21403496/merged_all.csv；
    目录或文件缺失时返回 None（测试标 BLOCKED）。
    """
    if zenodo_dir is None:
        return None
    p = zenodo_dir / "merged_all.csv"
    return p if p.exists() else None


# ---------- 合成常量（ATG-3 D-30~D-58） ----------
@pytest.fixture
def obj_decomp():
    """D-30：目标函数分解小解 F=10,C=20,P=5（TC-1.1.1）。"""
    return {"F": 10.0, "C": 20.0, "P": 5.0}


@pytest.fixture
def truck_energy_case():
    """D-33：卡车能耗公式常量（TC-3.6.1）。"""
    return {"theta": 0.1, "d": 100.0, "u": 50.0, "Q": 100.0,
            "alpha": 1.0, "beta": 2.0, "gamma": 0.5, "delta": 0.1}


@pytest.fixture
def vert_height_case():
    """D-35：垂直高度差 alt_i=10,alt_j=25（TC-3.8.1）。"""
    return {"alt_i": 10.0, "alt_j": 25.0}


@pytest.fixture
def load_update_case():
    """D-36：载荷更新 u_ijk=40,d^-=10,d^+=25（TC-3.9.1）。"""
    return {"u_ijk": 40.0, "d_minus": 10.0, "d_plus": 25.0}


@pytest.fixture
def gap_cases():
    """D-42：gap/可行性/改进率常量（TC-3.37/3.38/3.39）。"""
    return [
        {"f_alg": 120.0, "f_best": 100.0, "expected": 0.20},
        {"feas": 17, "total": 20, "expected": 0.85},
        {"f_init": 100.0, "f_final": 70.0, "expected": 0.30},
    ]


@pytest.fixture
def static_bad_samples():
    """D-44：静态检查 4 类禁止样本（TC-3.18.1）。"""
    return {
        "file_io": "def destroy(s,i,rng): return open('/x','w')",
        "infinite_loop": "def destroy(s,i,rng):\n while True: pass",
        "bad_return": "def destroy(s,i,rng): return 42",
        "network": "import requests\ndef destroy(s,i,rng): return requests.get('http://x')",
    }


@pytest.fixture
def anomaly_scenarios():
    """D-46：异常注入 3 场景（TC-3.44.1/2/3）。"""
    return ["syntax_inject", "interface_inject", "timeout_inject"]


@pytest.fixture
def preset_operators():
    """预置保守算子集合（AC-2.6/3.20）。"""
    return ["random_removal", "worst_removal", "shaw_removal"]


# ---------- 临时证据目录 ----------
@pytest.fixture
def tmp_evidence(tmp_path):
    d = tmp_path / "evidence"
    d.mkdir()
    return d


# ---------- 证据 9 字段样本（AC-2.4 / ATG-3 D-49） ----------
EVIDENCE_NINE = ["iteration_id", "timestamp", "llm_prompt_hash", "generated_code",
                 "execution_status", "objective_value", "feasibility_rate",
                 "runtime_ms", "recovery_action"]


@pytest.fixture
def sample_evidence(tmp_evidence):
    """写入一份含 9 必需字段的证据样本（D-49），供 TC-2.4.1/2、TC-4.1.1 读取。"""
    rec = {
        "iteration_id": 1,
        "timestamp": "2026-10-09T09:00:00Z",
        "llm_prompt_hash": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
        "generated_code": "def destroy(s,i,rng): ...",
        "execution_status": "completed",
        "objective_value": 1234.5,
        "feasibility_rate": 1.0,
        "runtime_ms": 45200,
        "recovery_action": None,
    }
    p = tmp_evidence / "round_1.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    return p
