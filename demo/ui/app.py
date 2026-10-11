"""ui/app.py — Streamlit console for SDVRPD LLM ALNS.

Start:
    cd demo
    streamlit run ui/app.py
"""
from __future__ import annotations
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from ui.theme import apply_theme, card, kpi_row
apply_theme()

st.markdown(
    "<div style='margin: 4px 0 18px 0;'>"
    "<h1 style='font-size:26px; color:#48cae4; letter-spacing:1px;'>"
    "🚁&ensp;SDVRPD · LLM 驱动 ALNS 求解台</h1>"
    "<div style='color:#7f95a8; font-size:13px; letter-spacing:.5px;'>"
    "Stochastic Drone-VRP · 混合 LLM/ALNS 启发式 · 科研控制台</div>"
    "</div>"
,
    unsafe_allow_html=True
)

raw_tab = st.sidebar.radio(
    "模块", ["🔧 配置", "⚙️ 求解", "📊 可视化"],
    key="ui_module_tab",
)
tab = raw_tab.split(" ", 1)[1]  # 去图标留功能名："配置"/"求解"/"可视化"


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
    def _config_body(s):
        from ui.config_tab import render_config_tab
        s.markdown("<div style='color:#7f95a8;font-size:13px;margin-bottom:8px;'>填写 LLM API 参数，保存后求解器自动调用 LLM 生成破坏算子。未配置时自动降级到预置算子。</div>", unsafe_allow_html=True)
        render_config_tab()

    card("LLM API 配置", _config_body)

elif tab == "求解":
    import glob
    inst_dir = os.path.join(PROJECT_ROOT, "data", "instances")
    insts = sorted(os.path.basename(p) for p in glob.glob(os.path.join(inst_dir, "*.json")))

    def _solve_caption(s):
        s.markdown(
            "<div style='color:#7f95a8;font-size:13px;'>"
            "选择实例与参数，运行 ALNS + LLM 混合求解；结果自动落盘并写入证据链。"
            "</div>",
            unsafe_allow_html=True,
        )

    card("单次求解 · ALNS + LLM", _solve_caption)

    if insts:
        sel = st.selectbox("选择实例", insts)
        tb = st.number_input("时间预算 (s)", min_value=5, max_value=300, value=30, step=5,
                             help="ALNS 路线搜索预算。程序会在接近限时时停止新一轮搜索；AI 接口等待和结果保存属于额外耗时。")
        seed = st.number_input("随机种子", min_value=0, max_value=99999, value=1, step=1)
        run_clicked = st.button("运行求解")

        if run_clicked:
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
                run_id = time.strftime("ui_%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
                out.update({
                    "run_id": run_id,
                    "instance_id": inst.get("instance_id", os.path.splitext(sel)[0]),
                    "instance_name": sel,
                    "time_budget": float(tb),
                    "seed": int(seed),
                    "recovery_action": llm_res.get("recovery_action"),
                    "llm_prompt_hash": llm_res.get("llm_prompt_hash", ""),
                    "llm_attempts": llm_res.get("attempts_log", []),
                    "llm_static_check": llm_res.get("static_check", {}),
                })
                results_dir = os.path.join(PROJECT_ROOT, "experiments", "results")
                os.makedirs(results_dir, exist_ok=True)
                result_path = os.path.join(results_dir, f"{run_id}_{out['instance_id']}_s{int(seed)}.json")
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, indent=2)
                with open(os.path.join(results_dir, "ui_last_result.json"), "w", encoding="utf-8") as f:
                    json.dump(out, f, ensure_ascii=False, indent=2)
                from verify.evidence import new_record, append_round
                evidence = new_record(
                    iteration_id=1,
                    stage="ui_run",
                    llm_prompt_hash=llm_res.get("llm_prompt_hash", ""),
                    generated_code=llm_res.get("generated_code", ""),
                    static_check=llm_res.get("static_check", {}),
                    execution={
                        "status": "completed",
                        "objective_value": out.get("objective_value"),
                        "feasibility_rate": out.get("feasibility_rate"),
                        "runtime_ms": out.get("runtime_ms"),
                    },
                    recovery_action=llm_res.get("recovery_action"),
                )
                evidence["run_id"] = run_id
                evidence["instance_id"] = out["instance_id"]
                evidence["attempts_log"] = llm_res.get("attempts_log", [])
                append_round(run_id, evidence)
                feas = out.get("feasibility_rate")
                feas_val = f"{feas*100:.1f}%" if feas is not None else "N/A"
                feas_status = "ok" if feas and feas >= 1.0 else "warn"
                iters = out.get("iterations", 0)
                obj = out.get("objective_value")
                obj_str = f"{obj:,.2f}" if obj is not None else "N/A"

                st.markdown("<div class='sci-title'>求解结果</div>", unsafe_allow_html=True)
                kpi_row([
                    ("目标值", obj_str, "info"),
                    ("可行性", feas_val, feas_status),
                    ("迭代", str(iters), "info"),
                    ("恢复模式", str(llm_res.get("recovery_action", "?")), "info"),
                ])
                if out.get("timed_out"):
                    st.info(f"已到达时间预算，保留当前最优解（实际搜索 {out.get('runtime_ms')} ms）")
                else:
                    st.success(f"求解完成 | recovery: {llm_res.get('recovery_action')}")
    else:
        st.warning("未找到实例 JSON。请先运行：python data/instance.py --force")

elif tab == "可视化":
    from ui.dashboard import render_dashboard
    render_dashboard()
