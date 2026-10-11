"""ui/solve_page.py —— 求解页：参数表单 + 实例摘要 + 运行状态与结果。

语义与原实现保持一致：
- run_llm_loop 生成 LLM 破坏算子（未启用时自动降级）。
- ALNSSolver(seed, time_budget, destroy_fn, use_checkpoint=True)。
- 结果写入 experiments/results/ 与 evidence/rounds/，并更新 ui_last_result.json 指针。

注意：右侧“最近一次结果”可能来自与当前选中实例不同的运行，页面明确标注其所属实例。
"""
from __future__ import annotations
import glob
import html
import json
import os

import streamlit as st

from ui.components import (section_title, metric_row, status_badge, empty_state,
                           kv_list, notice, panel_label)
from ui import state as S

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
INST_DIR = os.path.join(PROJECT_ROOT, "data", "instances")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "experiments", "results")


def _list_instances():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(INST_DIR, "*.json")))


def _load_instance(name):
    try:
        with open(os.path.join(INST_DIR, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _run_solve(inst, tb, seed, on_phase=None):
    from solver.alns import ALNSSolver
    from solver.model import load_params
    from llm.closed_loop import run_llm_loop

    params = load_params()
    if on_phase:
        on_phase("生成与校验模型算子")
    llm_res = run_llm_loop(inst, current_objective=0.0, current_unassigned=[], round_no=1)
    if on_phase:
        on_phase("搜索路线方案")
    solver = ALNSSolver(
        inst, params=params, seed=int(seed), time_budget=float(tb),
        destroy_fn=llm_res["destroy_fn"] if llm_res.get("recovery_action") == "llm_ok" else None,
        use_checkpoint=True,
    )
    return solver.run(), llm_res


def _persist(out, llm_res, inst, inst_name, tb, seed):
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
    ev = new_record(
        iteration_id=1, stage="ui_run",
        llm_prompt_hash=llm_res.get("llm_prompt_hash", ""),
        generated_code=llm_res.get("generated_code", ""),
        static_check=llm_res.get("static_check", {}),
        execution={"status": "completed", "objective_value": out.get("objective_value"),
                   "feasibility_rate": out.get("feasibility_rate"),
                   "runtime_ms": out.get("runtime_ms")},
        recovery_action=llm_res.get("recovery_action"),
    )
    ev["run_id"] = run_id
    ev["instance_id"] = out["instance_id"]
    ev["attempts_log"] = llm_res.get("attempts_log", [])
    append_round(run_id, ev)
    return run_id


def _status_of(out):
    if not out:
        return ("idle", "未开始")
    if out.get("timed_out"):
        return ("warn", "已到预算而停止")
    return ("ok", "已完成")


def _metrics(out):
    obj = out.get("objective_value")
    init = out.get("initial_objective")
    feas = out.get("feasibility_rate")
    gain = f"{(init - obj) / init * 100:.2f}" if (obj is not None and init) else None
    rt = out.get("runtime_ms")
    return [
        ("最优目标值", f"{obj:,.2f}" if obj is not None else None, "元", "", True),
        ("相对初始改善", gain, "%", "ok" if gain and float(gain) > 0 else "", False),
        ("可行性", f"{feas*100:.0f}" if feas is not None else None, "%",
         "ok" if feas and feas >= 1.0 else "warn", False),
        ("搜索耗时", f"{rt/1000:.1f}" if rt is not None else None, "s", "", False),
    ]


def _recent_result(last, current_inst_name):
    """右侧最近一次结果；明确标注它属于哪次运行、哪个实例。"""
    if not last:
        empty_state("尚无运行结果",
                    "在左侧选择实例并开始求解后，这里会显示该次运行的关键指标。")
        return
    state, label = _status_of(last)
    res_inst = last.get("instance_name") or last.get("instance_id") or "未知实例"
    stale = bool(current_inst_name) and res_inst != current_inst_name

    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'gap:12px;margin-bottom:10px;">'
        f'<span style="font-size:13px;font-weight:600;color:#182235;">历史运行结果</span>'
        f'{status_badge(state, label)}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:12.5px;color:#69778A;margin:-4px 0 10px 0;line-height:1.55;">'
        f'来自运行 <span style="color:#3659D9;">{html.escape(str(last.get("run_id", "—")))}</span>，'
        f'实例 <span style="color:#182235;">{html.escape(str(res_inst))}</span></div>',
        unsafe_allow_html=True)
    if stale:
        notice(f"该结果来自实例 {res_inst}，与当前选中的 {current_inst_name} 不同，"
               f"请勿与本次运行的预期混用。", "warn")

    metric_row(_metrics(last))
    st.write("")
    kv_list([
        ("迭代次数", last.get("iterations")),
        ("随机种子", last.get("seed"), True),
        ("未服务客户", len(last.get("unassigned") or [])),
        ("算子来源", {"llm_ok": "LLM 生成成功"}.get(last.get("recovery_action"),
                                                    last.get("recovery_action") or "—")),
    ])
    if last.get("timed_out"):
        st.write("")
        notice("本次搜索在时间预算附近停止，已保留当前最优解；"
               "AI 接口等待与结果保存不计入搜索预算。")


def _open_results():
    st.session_state["requested_nav"] = "结果分析"


def _begin_solve():
    st.session_state["solve_busy"] = True
    st.session_state.pop("solve_error", None)


def render():
    insts = _list_instances()
    if not insts:
        empty_state("未找到实例文件",
                    "请先运行 python data/instance.py --force 生成实例 JSON，再回到本页。")
        return

    last = S.load_last_result()
    left, right = st.columns([1, 1.15], gap="large")

    with left:
        section_title("求解参数")
        with st.form("solve_form", clear_on_submit=False):
            sel = st.selectbox("实例", insts,
                               help="数据目录下的实例文件；长文件名在选项中可完整查看。")
            c1, c2 = st.columns([1, 1])
            with c1:
                tb = st.number_input("时间预算", min_value=5, max_value=300, value=30,
                                     step=5, help="单位：秒。ALNS 路线搜索预算。")
            with c2:
                st.markdown('<div style="height:28px"></div>', unsafe_allow_html=True)
                st.caption("秒（ALNS 路线搜索预算）")
            with st.expander("高级参数", expanded=False):
                seed = st.number_input("随机种子", min_value=0, max_value=99999,
                                       value=1, step=1,
                                       help="固定种子控制随机选择；实际完成的迭代数量仍受时间预算影响。")
            submitted = st.form_submit_button(
                "开始求解", type="primary", on_click=_begin_solve,
                disabled=st.session_state.get("solve_busy", False))

    with right:
        section_title("实例摘要")
        meta = _load_instance(sel)
        if meta:
            kv_list([
                ("实例编号", meta.get("instance_id"), True),
                ("节点数", meta.get("num_nodes") or len(meta.get("nodes") or [])),
                ("无人机数", meta.get("num_drones")),
                ("空域", meta.get("airspace")),
                ("源文件", meta.get("filename")),
            ])
        else:
            empty_state("无法读取实例元数据", "所选实例文件无法解析，请检查文件是否完整。")

        st.write("")
        st.write("")
        _recent_result(last, sel)

    if st.session_state.get("solve_error"):
        st.error("求解失败：" + st.session_state["solve_error"])
        st.caption("参数已保留，修正后可再次点击“开始求解”重试。")

    if submitted:
        st.write("")
        run_state = st.status("正在求解…", expanded=True)
        try:
            inst = _load_instance(sel)
            if inst is None:
                raise ValueError("实例文件无法解析")
            def phase(label):
                run_state.update(label=label, state="running")
                with run_state:
                    st.write(label)
            out, llm_res = _run_solve(inst, tb, int(seed), on_phase=phase)
            run_id = _persist(out, llm_res, inst, sel, tb, int(seed))
            state, label = _status_of(out)
            run_state.update(label=f"求解结束 · {label}",
                             state="error" if state == "danger" else "complete",
                             expanded=True)
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
            st.session_state["solve_error"] = f"{type(e).__name__}: {e}"
        finally:
            st.session_state["solve_busy"] = False
        st.rerun()

    if st.session_state.get("after_solve"):
        out = S.load_last_result() or {}
        state, label = _status_of(out)
        st.write("")
        section_title("本次运行结果")
        st.markdown(f'<div style="margin:-6px 0 12px 0;">{status_badge(state, label)}</div>',
                    unsafe_allow_html=True)
        metric_row(_metrics(out))
        st.write("")
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            st.button("查看结果", type="primary", use_container_width=True, on_click=_open_results)
        with c2:
            st.download_button(
                "导出结果 JSON",
                data=json.dumps(out, ensure_ascii=False, indent=2),
                file_name=f"{out.get('run_id', 'result')}.json",
                mime="application/json", use_container_width=True,
            )
        if out.get("recovery_action") and out["recovery_action"] != "llm_ok":
            st.caption("本次未使用 LLM 算子（"
                       f"{out['recovery_action']}），已回退到预置算子；可在“模型配置”页启用。")
