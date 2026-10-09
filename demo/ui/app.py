"""ui/app.py —— Streamlit 控制台（FR-15/16 / T-10 + T-15）。

T-10 实现：配置 Tab（LLM API 读写）。
T-15 将扩展：四个可视化视图（路径地图/收敛曲线/算子热力/LLM 时间线）+ 证据导出。

启动方式：
    cd demo
    streamlit run ui/app.py
"""
from __future__ import annotations
import os
import sys

# 确保项目根在 sys.path（让 config_tab / llm / verify 等可导入）
BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

st.set_page_config(page_title="SDVRPD LLM 驱动 ALNS 控制台", page_icon="🚁")
st.title("SDVRPD LLM 驱动 ALNS 求解器控制台")

# ---- 侧边栏 Tab 选择 ----
tab = st.sidebar.radio("模块", ["配置", "求解", "可视化"])

if tab == "配置":
    from ui.config_tab import render_config_tab
    render_config_tab()

elif tab == "求解":
    st.subheader("单次求解")
    import json, glob
    inst_dir = os.path.join(PROJECT_ROOT, "data", "instances")
    insts = sorted(os.path.basename(p) for p in glob.glob(os.path.join(inst_dir, "*.json")))
    if not insts:
        st.warning("未找到实例 JSON。请先运行：python data/instance.py --force")
    else:
        sel = st.selectbox("选择实例", insts)
        tb = st.number_input("时间预算 (s)", 5, 300, 30)
        seed = st.number_input("随机种子", 0, 99999, 1)
        if st.button("运行求解"):
            with st.spinner("ALNS 求解中..."):
                from solver.alns import ALNSSolver
                from solver.model import load_params
                from llm.closed_loop import run_llm_loop
                inst = json.load(open(os.path.join(inst_dir, sel), encoding="utf-8"))
                params = load_params()
                # LLM 闭环（无配置自动降级）
                llm_res = run_llm_loop(inst, current_objective=0.0, current_unassigned=[], round_no=1)
                solver = ALNSSolver(inst, params=params, seed=int(seed),
                                    time_budget=float(tb),
                                    destroy_fn=llm_res["destroy_fn"] if llm_res["recovery_action"] == "llm_ok" else None,
                                    use_checkpoint=True)
                out = solver.run()
                st.json({k: out[k] for k in ("objective_value", "feasibility_rate",
                                               "iterations", "runtime_ms", "unassigned")})
                st.success(f"求解完成 | recovery: {llm_res['recovery_action']}")

elif tab == "可视化":
    from ui.dashboard import render_dashboard
    render_dashboard()
