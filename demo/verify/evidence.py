"""verify/evidence.py —— 证据链保存（FR-10 / D3 / AC-6.1 / EC-8）。

每轮迭代产生一条结构化证据记录，字段对应设计文档 2.4 证据链保存策略：
  iteration_id, timestamp, llm_prompt_hash, generated_code,
  static_check{passed,signature_ok,forbidden_patterns},
  execution{status,objective_value,feasibility_rate,runtime_ms},
  recovery_action

证据写入 evidence/ 目录，JSON 单文件/追加，字段完整可追溯（NFR-3）。
保存失败（磁盘/权限）不阻塞主流程（EC-8）：捕获异常并记录警告。
"""
from __future__ import annotations
import json
import os
import time
import hashlib

BASE = os.path.dirname(os.path.abspath(__file__))
EVIDENCE_DIR = os.path.join(BASE, "..", "evidence")


def _ensure_dir():
    os.makedirs(EVIDENCE_DIR, exist_ok=True)


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()[:16]


def new_record(**kw) -> dict:
    """构造一条证据记录骨架，缺失字段填默认值（保证 AC-6.1 字段齐全）。"""
    rec = {
        "iteration_id": kw.get("iteration_id", 0),
        "timestamp": kw.get("timestamp", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        "stage": kw.get("stage", "alns_execution"),
        "llm_prompt_hash": kw.get("llm_prompt_hash", ""),
        "generated_code": kw.get("generated_code", ""),
        "static_check": kw.get("static_check", {
            "passed": None, "signature_ok": None, "forbidden_patterns": []}),
        "execution": kw.get("execution", {
            "status": "unknown", "objective_value": None,
            "feasibility_rate": None, "runtime_ms": None}),
        "recovery_action": kw.get("recovery_action", None),
    }
    return rec


def save_record(record: dict, subdir: str = "") -> str:
    """写一条证据记录到 evidence/（按 iteration 分文件）。失败返回 None（EC-8）。"""
    try:
        _ensure_dir()
        out_dir = os.path.join(EVIDENCE_DIR, subdir) if subdir else EVIDENCE_DIR
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"iter_{record['iteration_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return path
    except Exception as e:
        print(f"[evidence] 保存失败（降级继续）: {type(e).__name__}: {e}")
        return None


def append_round(round_id: str, record: dict) -> str:
    """按轮次分组保存（对应 D5 平台记录，一轮 = 多次迭代）。"""
    try:
        _ensure_dir()
        out_dir = os.path.join(EVIDENCE_DIR, "rounds", round_id)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"iter_{record['iteration_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
        return path
    except Exception as e:
        print(f"[evidence] 轮次保存失败（降级继续）: {type(e).__name__}: {e}")
        return None


def list_rounds() -> list:
    r = os.path.join(EVIDENCE_DIR, "rounds")
    if not os.path.isdir(r):
        return []
    return sorted(os.listdir(r))


if __name__ == "__main__":
    rec = new_record(iteration_id=0, stage="demo",
                     execution={"status": "ok", "objective_value": 1.0,
                                 "feasibility_rate": 1.0, "runtime_ms": 10})
    p = save_record(rec)
    print("saved demo evidence ->", p)
