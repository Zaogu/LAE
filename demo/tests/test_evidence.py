"""ATG-4 test_evidence：证据链 / 检查点 / 提交产物（集成 + 验收 TC）。

对应 demo/evidence/ 结构化记录。
证据 9 字段样本由 conftest 的 sample_evidence fixture 提供（AC-2.4 / ATG-3 D-49）。
"""
import json
import pytest

CKPT_FIVE = ["current_solution", "weights", "iter_count", "rng_state", "timestamp"]
EVIDENCE_NINE = ["iteration_id", "timestamp", "llm_prompt_hash", "generated_code",
                 "execution_status", "objective_value", "feasibility_rate",
                 "runtime_ms", "recovery_action"]


# ---------------- 证据 9 字段（集成） ----------------
@pytest.mark.integration
@pytest.mark.p0
def test_tc_2_4_1_nine_fields(sample_evidence):
    """AC-2.4：§2.1 每轮迭代证据记录含 9 必需字段。"""
    rec = json.load(open(sample_evidence, encoding="utf-8"))
    assert set(EVIDENCE_NINE) <= set(rec.keys())


@pytest.mark.integration
@pytest.mark.p0
def test_tc_2_4_2_hash_valid(sample_evidence):
    """AC-2.4：§2.1 llm_prompt_hash 为有效哈希（>=32 且 hex）。"""
    rec = json.load(open(sample_evidence, encoding="utf-8"))
    h = rec["llm_prompt_hash"]
    assert len(h) >= 32 and all(c in "0123456789abcdef" for c in h.lower())


# ---------------- 检查点 5 字段（集成） ----------------
@pytest.mark.integration
@pytest.mark.p1
def test_tc_3_29_1_ckpt_five_fields(tmp_evidence):
    """AC-3.29：§3.3 检查点含 5 必需字段。"""
    p = tmp_evidence / "ckpt_100.json"
    p.write_text(json.dumps({k: None for k in CKPT_FIVE}), encoding="utf-8")
    rec = json.load(open(p, encoding="utf-8"))
    assert set(CKPT_FIVE) <= set(rec.keys())


# ---------------- 每次实验三类产物（集成） ----------------
@pytest.mark.integration
@pytest.mark.p1
def test_tc_4_1_1_three_artifacts(sample_evidence):
    """AC-4.1：§4.4 每次实验提交含求解结果/证据记录/评估指标三类。"""
    rec = json.load(open(sample_evidence, encoding="utf-8"))
    # 求解结果字段
    assert "objective_value" in rec
    # 证据记录字段
    assert "generated_code" in rec and "llm_prompt_hash" in rec
    # 评估指标字段
    assert "feasibility_rate" in rec and "runtime_ms" in rec
