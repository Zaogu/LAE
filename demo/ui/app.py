"""ui/app.py — Streamlit console for SDVRPD LLM ALNS.

Start:
    cd demo
    streamlit run ui/app.py
"""
from __future__ import annotations
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

st.set_page_config(page_title="SDVRPD LLM ALNS console", page_icon="🚁")
st.title("SDVRPD LLM 驱动 ALNS 求解器控制台")

tab = st.sidebar.radio("模块", ["配置", "求解", "可视化"])


def _json_safe(obj, depth: int = 0):
    if depth > 12:
        return "<truncated>"
    if isinstance(obj, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v, depth + 1) for v in list(obj)[:2000]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


if tab == "配置":
    from ui.config_tab import render_config_tab
    render_config_tab()

elif tab == "求解":
    st.subheader("单次求解")
    import glob
    inst_dir = os.path.join(PROJECT_ROOT, "data", "instances")
    insts = sorted(os.path.basename(p) for p in glob.glob(os.path.join(inst_dir, "*.json")))
    if not insts:
        st.warning("未找到实例 JSON。请先运行：python data/instance.py --force")
    else:
        sel = st.selectbox("选择实例", insts)
        tb = st.number_input("时间预算 (s)", min_value=5, max_value=300, value=30, step=5)
        seed = st.number_input("随机种子", min_value=0, max_value=99999, value=1, step=1)
        if st.button("运行求解"):
            with st.spinner("ALNS 求解中..."):
                from solver.alns import ALNSSolver
                from solver.model import load_params
                from llm.closed_loop import run_llm_loop
                fp = os.path.join(inst_dir, sel)
                with open(fp, encoding="utf-8") as f:
                    inst = json.load(f)
                params = load_params()
                llm_res = run_llm_loop(inst, current_objective=0.0, current_unassigned=[], round_no=1)
                solver = ALNSSolver(
                    inst,
                    params=params,
                    seed=int(seed),
                    time_budget=float(tb),
                    destroy_fn=llm_res["destroy_fn"] if llm_res.get("recovery_action") == "llm_ok" else None,
                    use_checkpoint=True,
                )
                out = solver.run()
                st.json(_json_safe({
                    "objective_value": out.get("objective_value"),
                    "feasibility_rate": out.get("feasibility_rate"),
                    "iterations": out.get("iterations"),
                    "runtime_ms": out.get("runtime_ms"),
                    "unassigned": out.get("unassigned"),
                    "recovery_action": llm_res.get("recovery_action"),
                }))
                st.success(f"求解完成 | recovery: {llm_res.get('recovery_action')}")

elif tab == "可视化":
    from ui.dashboard import render_dashboard
    render_dashboard()
