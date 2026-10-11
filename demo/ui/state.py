"""ui/state.py —— 数据加载与会话状态小工具（只读，无副作用）。

统一 results / evidence 的读取口径，供求解页与结果分析页复用。
"""
from __future__ import annotations
import glob
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "experiments", "results")
INST_DIR = os.path.join(PROJECT_ROOT, "data", "instances")
EVIDENCE_DIR = os.path.join(PROJECT_ROOT, "evidence")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def load_last_result():
    """当前运行结果：优先 ui_last_result.json 指针，其次最新 ui_*.json。"""
    ptr = os.path.join(RESULTS_DIR, "ui_last_result.json")
    if os.path.isfile(ptr):
        obj = _read_json(ptr)
        if obj:
            return obj
    cands = sorted(glob.glob(os.path.join(RESULTS_DIR, "ui_*.json")),
                   key=os.path.getmtime, reverse=True)
    for p in cands:
        obj = _read_json(p)
        if obj:
            return obj
    return None


def load_result_by_run(run_id):
    """按 run_id 载入某个结果文件。"""
    if not run_id:
        return None
    pattern = os.path.join(RESULTS_DIR, f"{run_id}_*.json")
    matches = glob.glob(pattern)
    if os.path.isfile(os.path.join(RESULTS_DIR, "ui_last_result.json")):
        last = _read_json(os.path.join(RESULTS_DIR, "ui_last_result.json"))
        if last and last.get("run_id") == run_id:
            return last
    for p in matches:
        obj = _read_json(p)
        if obj and obj.get("run_id") == run_id:
            return obj
    return None


def list_results():
    """全部结果文件摘要，按修改时间倒序。"""
    out = []
    for p in glob.glob(os.path.join(RESULTS_DIR, "*.json")):
        name = os.path.basename(p)
        if name in ("ui_last_result.json", "report.json"):
            continue
        obj = _read_json(p)
        if not obj:
            continue
        obj["_path"] = p
        obj["_mtime"] = os.path.getmtime(p)
        out.append(obj)
    out.sort(key=lambda r: r.get("_mtime", 0), reverse=True)
    return out


def load_instance(instance_id):
    if not instance_id:
        return None
    p = os.path.join(INST_DIR, f"{instance_id}.json")
    return _read_json(p) if os.path.isfile(p) else None


def load_default_instance():
    for p in sorted(glob.glob(os.path.join(INST_DIR, "*.json"))):
        obj = _read_json(p)
        if obj:
            return obj
    return None


def load_evidence(run_id=None):
    """载入证据记录；给 run_id 时只取该运行。"""
    recs = []
    patterns = [
        os.path.join(EVIDENCE_DIR, "iter_*.json"),
        os.path.join(EVIDENCE_DIR, "rounds", "**", "iter_*.json"),
    ]
    for pat in patterns:
        for p in glob.glob(pat, recursive=True):
            obj = _read_json(p)
            if obj:
                recs.append(obj)
    if run_id:
        recs = [r for r in recs if str(r.get("run_id") or "") == str(run_id)]
    recs.sort(key=lambda r: (r.get("timestamp") or "", r.get("iteration_id") or 0))
    return recs


# ---- session helpers ------------------------------------------------------
def set_last_result(out):
    import streamlit as st
    st.session_state["last_out"] = out


def get_last_result():
    import streamlit as st
    return st.session_state.get("last_out")
