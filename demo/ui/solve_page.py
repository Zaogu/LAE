"""ui/solve_page.py —— 求解页：参数表单 + 实例摘要 + 运行状态与结果。

语义与原 ui/app.py 保持一致：
- 调用 run_llm_loop 生成 LLM 破坏算子（未启用时自动降级）。
- ALNSSolver(seed, time_budget, destroy_fn, use_checkpoint=True)。
- 结果写入 experiments/results/ 与 evidence/rounds/，并更新 ui_last_result.json 指针。
"""
from __future__ import annotations
import glob
import json
import os

import streamlit as st

from ui.components import (section_title, metric_row, status_badge, empty_state, kv_list)
from ui import state as S

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
INST_DIR = os.path.join(PROJECT_ROOT, "data", "instances")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "experiments", "results")


def _list_instances():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(INST_DIR, "*.json")))


def _load_instance_meta(name):
    try:
        with open(os.path.join(INST_DIR, name), encoding="utf-8") as f:
            inst = json.load(f)
    except Exception:
        return None
    return inst


def _run_solve(inst_path, inst, tb, seed):
    """执行一次求解，返回 (out, llm_res)。语义与原实现一致。"""
    from solver.alns import ALNSSolver
    from solver.model import load_params
    from llm.closed_loop import run_llm_loop

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
    return out, llm_res


def _persist(out, llm_res, inst, inst_name, tb, seed):
    """持久化结果与证据，返回 run_id。语义与原实现一致。"""
    import time
    run_id = time.strftime("ui_%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"
    out.update({
        "run_id": run_id,
        "instance_id": inst.get("instance_id", os.path.splitext(inst_name)[0]),
        "instance_name": inst_name,
        "time_budget": float(tb),
        "seed": int(seed),
        "recovery_action": llm_res.get("recovery_action"),
        "llm_prompt_hash": llm_res.get("llm_prompt_hash", ""),
        "llm_attempts": llm_res.get("attempts_log", []),
        "llm_static_check": llm_res.get("static_check", {}),
    })
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"{run_id}_{out['instance_id']}_s{int(seed)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    with open(os.path.join(RESULTS_DIR, "ui_last_result.json"), "w", encoding="utf-8") as f:
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
    return run_id


def _fmt_run_status(out):
    if not out:
        return ("idle", "未开始")
    if out.get("timed_out"):
        return ("warn", "已到时间预算而停止")
    return ("ok", "已完成")


def _render_last_result(out, llm_res):
    """右侧：最近一次真实结果摘要。"""
    if not out:
        empty_state("尚无运行结果", "在左侧选择实例并开始求解后，这里会显示本次运行的关键指标。")
        return
    state, label = _fmt_run_status(out)
    st.markdown(status_badge(state, label), unsafe_allow_html=True)
    st.write("")
    obj = out.get("objective_value")
    init = out.get("initial_objective")
    feas = out.get("feasibility_rate")
    gain = None
    if obj is not None and init:
        gain = f"{(init - obj) / init * 100:.2f}"
    metric_row([
        ("最优目标值", f"{obj:,.2f}" if obj is not None else None, "元", ""),
        ("相对初始改善", gain, "%", "ok" if gain and float(gain) > 0 else ""),
        ("可行性", f"{feas*100:.0f}" if feas is not None else None, "%",
         "ok" if feas and feas >= 1.0 else "warn"),
        ("搜索耗时", f"{out.get('runtime_ms', 0)/1000:.1f}" if out.get("runtime_ms") is not None else None,
         "s", ""),
    ])
    st.write("")
    rows = [
        ("实例", out.get("instance_name") or out.get("instance_id")),
        ("迭代次数", out.get("iterations")),
        ("随机种子", out.get("seed"), True),
        ("运行编号", out.get("run_id"), True),
        ("算子来源", {"llm_ok": "LLM 生成成功"}.get(out.get("recovery_action"),
                                                    out.get("recovery_action"))),
        ("未服务客户", len(out.get("unassigned") or [])),
    ]
    kv_list(rows)
    if out.get("timed_out"):
        st.caption("说明：在时间预算附近停止，保留当前最优解；AI 接口等待与结果保存不计入搜索预算。")


def render():
    insts = _list_instances()
    if not insts:
        empty_state("未找到实例文件",
                    "请先运行 python data/instance.py --force 生成实例 JSON，再回到本页。")
        return

    last = S.load_last_result()
    left, right = st.columns([1.15, 1], gap="large")

    with left:
        section_title("求解参数")
        with st.form("solve_form", clear_on_submit=False):
            sel = st.selectbox(
                "实例", insts,
                help="选择数据目录下的实例文件；文件名过长时可在选项中查看完整名称。",
            )
            tb = st.number_input(
                "时间预算（秒）", min_value=5, max_value=300, value=30, step=5,
                help="ALNS 路线搜索预算。程序在接近限时时停止新一轮搜索；AI 接口等待与结果保存属于额外耗时。",
            )
            with st.expander("高级参数", expanded=False):
                seed = st.number_input("随机种子", min_value=0, max_value=99999, value=1, step=1,
                                       help="相同种子与相同预算下，求解过程可复现。")
            submitted = st.form_submit_button("开始求解", type="primary", use_container_width=True)

    with right:
        section_title("实例摘要")
        meta = _load_instance_meta(sel)
        if meta:
            meta_rows = [
                ("实例编号", meta.get("instance_id"), True),
                ("节点数", meta.get("num_nodes") or len(meta.get("nodes") or [])),
                ("无人机数", meta.get("num_drones")),
                ("空域", meta.get("airspace")),
                ("垂直模式", meta.get("vertical")),
                ("源文件", meta.get("filename")),
            ]
            kv_list(meta_rows)
        else:
            empty_state("无法读取实例元数据", "所选实例文件无法解析，请检查文件是否完整。")

        st.write("")
        section_title("最近一次结果")
        _render_last_result(last, None)

    st.write("")
    st.divider()

    # 运行状态区
    if submitted:
        run_state = st.status("正在求解…", expanded=True)
        try:
            inst = _load_instance_meta(sel)
            if inst is None:
                raise ValueError("实例文件无法解析")
            with run_state:
                st.write("· 生成 / 校验 LLM 破坏算子")
                st.write("· 运行 ALNS 路线搜索")
            out, llm_res = _run_solve(os.path.join(INST_DIR, sel), inst, tb, int(seed))
            run_id = _persist(out, llm_res, inst, sel, tb, int(seed))
            state, label = _fmt_run_status(out)
            run_state.update(
                label=f"求解结束 · {label}",
                state="complete" if state == "ok" else "error" if state == "danger" else "complete",
                expanded=True,
            )
            with run_state:
                st.write(f"· 运行编号：`{run_id}`")
                st.write(f"· 实际搜索耗时：{out.get('runtime_ms')} ms")
            S.set_last_result(out)
            st.session_state["after_solve"] = True
        except Exception as e:
            run_state.update(label="求解失败", state="error", expanded=True)
            with run_state:
                st.error(f"{type(e).__name__}: {e}")
                st.caption("参数已保留，修正后可再次点击“开始求解”重试。")
            st.session_state["after_solve"] = False

    if st.session_state.get("after_solve"):
        out = S.load_last_result() or {}
        state, label = _fmt_run_status(out)
        section_title("本次运行结果")
        st.markdown(status_badge(state, label), unsafe_allow_html=True)
        st.write("")
        obj = out.get("objective_value")
        init = out.get("initial_objective")
        gain = f"{(init - obj) / init * 100:.2f}" if (obj is not None and init) else None
        metric_row([
            ("最优目标值", f"{obj:,.2f}" if obj is not None else None, "元", ""),
            ("相对初始改善", gain, "%", "ok" if gain and float(gain) > 0 else ""),
            ("可行性", f"{out.get('feasibility_rate', 0)*100:.0f}"
             if out.get("feasibility_rate") is not None else None, "%", "ok"),
            ("迭代次数", out.get("iterations"), "", ""),
        ])
        st.write("")
        c1, c2, _ = st.columns([1, 1, 3])
        if c1.button("查看结果", type="primary", use_container_width=True):
            st.session_state["nav_page"] = "结果分析"
            st.rerun()
        with c2:
            st.download_button(
                "导出结果 JSON",
                data=json.dumps(out, ensure_ascii=False, indent=2),
                file_name=f"{out.get('run_id', 'result')}.json",
                mime="application/json",
                use_container_width=True,
            )
        if out.get("recovery_action") and out["recovery_action"] != "llm_ok":
            st.caption("本次未使用 LLM 算子（"
                       f"{out['recovery_action']}），已回退到预置算子；可在“模型配置”页启用。")
