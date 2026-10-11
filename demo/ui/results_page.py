"""ui/results_page.py —— 结果分析页：围绕当前运行组织的工作区。

标签页：路径 / 搜索过程 / 生成记录 / 导出。
- 顶部：实例、运行时间、运行编号、状态组成的标题信息区。
- 指标条：最优目标值作为视觉重点，其余指标较轻。
- 路径：2D / 3D 切换，路径图与右侧路径摘要同一分析区、顶部对齐。
- 搜索过程：收敛曲线 + 算子表现。
- 生成记录：LLM 生成时间线（紧凑表格 + 按需展开详情）。
- 导出：可检索的运行记录表格 + 当前运行导出 + 全量导出。

数值与单位沿用求解器输出，不擅自换算；内部编号收进“开发详情”。
"""
from __future__ import annotations
import html
import glob
import json
import os

import streamlit as st

from ui.components import (section_title, metric_row, status_badge, empty_state,
                           kv_list, path_legend, notice)
from ui import state as S
from ui import charts

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _fmt_status(out):
    if not out:
        return ("idle", "未开始")
    if out.get("timed_out"):
        return ("warn", "已到预算而停止")
    return ("ok", "已完成")


def _fmt_ts(ts):
    if not ts:
        return None
    return str(ts).replace("T", " ").replace("Z", " UTC")


def _run_rows():
    rows = []
    for r in S.list_results():
        ev = S.load_evidence(r.get("run_id"))
        _, label = _fmt_status(r)
        ts = next((e.get("timestamp") for e in ev if e.get("timestamp")), None)
        if not ts:
            import datetime
            ts = datetime.datetime.fromtimestamp(r.get("_mtime", 0)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append({
            "运行名称": r.get("instance_name") or r.get("instance_id") or "—",
            "运行时间": _fmt_ts(ts),
            "状态": label,
            "证据数量": len(ev),
            "目标值": r.get("objective_value"),
            "迭代": r.get("iterations"),
            "运行编号": r.get("run_id"),
            "_run_id": r.get("run_id"),
        })
    return rows


def render():
    result = S.load_last_result()
    if not result:
        empty_state("尚无结果数据",
                    "请先在“求解”页运行一个实例；完成后本页会显示路径方案、搜索过程与证据。")
        return

    inst_id = result.get("instance_id")
    inst = S.load_instance(inst_id)
    run_id = result.get("run_id")
    state, label = _fmt_status(result)
    ev = S.load_evidence(run_id)
    ts = next((e.get("timestamp") for e in ev if e.get("timestamp")), None)
    inst_name = result.get("instance_name") or inst_id or "未知实例"

    # ---- 标题信息区 ----
    st.markdown(
        '<div class="run-context"><div>'
        f'<div class="name">{html.escape(str(inst_name))}</div>'
        f'<div class="detail">运行时间 {html.escape(str(_fmt_ts(ts) or "—"))}<br>'
        f'运行编号 <span class="mono">{html.escape(str(run_id or "—"))}</span>'
        f'</div></div>{status_badge(state, label)}</div>', unsafe_allow_html=True)

    obj = result.get("objective_value")
    init = result.get("initial_objective")
    feas = result.get("feasibility_rate")
    rt_ms = result.get("runtime_ms")
    gain = f"{(init - obj) / init * 100:.2f}" if (obj is not None and init) else None
    metric_row([
        ("最优目标值", f"{obj:,.2f}" if obj is not None else None, "元", "", True),
        ("相对初始改善", gain, "%", "ok" if gain and float(gain) > 0 else "", False),
        ("搜索耗时", f"{rt_ms/1000:.1f}" if rt_ms is not None else None, "s", "", False),
        ("迭代次数", result.get("iterations"), "", "", False),
        ("可行性", f"{feas*100:.0f}" if feas is not None else None, "%",
         "ok" if feas and feas >= 1.0 else "warn", False),
    ])

    # 紧凑辅助信息
    msgs = []
    if result.get("timed_out"):
        msgs.append("在时间预算附近停止，已保留当前最优解；"
                    "AI 接口等待与结果保存不计入搜索预算。")
    if result.get("invalid_candidates"):
        msgs.append(f"本次拦截 {result['invalid_candidates']} 个不可行候选方案，"
                    "最终结果只保留通过检查的路线。")
    if inst:
        from solver.model import validate_routes
        v = validate_routes(result.get("paths"), result.get("unassigned"), inst)
        if not v["passed"]:
            st.write("")
            st.error("当前保存结果未通过路线完整性检查：" + "；".join(v["errors"]) +
                     "。请在求解页重新运行后再分析。")
    if msgs:
        st.write("")
        notice("　".join(msgs), "warn")

    st.write("")
    tab_path, tab_conv, tab_gen, tab_export = st.tabs(["路径", "搜索过程", "生成记录", "导出"])

    with tab_path:
        view = st.radio("视图", ["2D 路径", "3D 空域"], horizontal=True,
                        label_visibility="collapsed", key="path_view")
        c_main, c_side = st.columns([3, 1], gap="large")
        with c_main:
            section_title("路径视图")
            if not inst:
                empty_state("缺少实例数据", "无法加载该运行的实例文件，路径视图不可用。")
            elif view == "2D 路径":
                st.plotly_chart(charts.path_map_2d(result, inst), use_container_width=True,
                                config={"displaylogo": False, "scrollZoom": True})
            else:
                st.plotly_chart(charts.path_map_3d(result, inst), use_container_width=True,
                                config={"displaylogo": False, "scrollZoom": True})
        with c_side:
            section_title("路径摘要")
            paths = result.get("paths") or []
            total = sum(len([x for x in p if x != 0]) for p in paths if isinstance(p, list))
            kv_list([
                ("路径数", len(paths)),
                ("客户总数", total),
                ("未服务客户", len(result.get("unassigned") or [])),
                ("可行性", "可行" if (feas or 0) >= 1.0 else "存在缺口"),
            ])
            st.write("")
            path_legend(paths)
            if view == "3D 空域":
                st.caption("可拖拽旋转、滚轮缩放；双击图内重置视角。")

    with tab_conv:
        section_title("收敛过程")
        history = result.get("history") or []
        values = [h["objective"] for h in history if h.get("objective") is not None]
        flat = bool(values) and len(set(values)) == 1
        show_candidates = st.checkbox("显示当前解与候选方案", value=True, key="show_search_candidates")
        st.plotly_chart(charts.convergence(history, show_candidates=show_candidates), use_container_width=True,
                        config={"displaylogo": False})
        if flat:
            st.caption(f"本次完成 {result.get('iterations', 0)} 次迭代，未找到更优解，"
                       "历史最优曲线保持平直；当前解与候选方案反映真实搜索尝试。")
        if history:
            candidates = [h["candidate_objective"] for h in history
                          if h.get("candidate_objective") is not None]
            accepted = sum(bool(h.get("accepted")) for h in history)
            restarts = result.get("search_restarts")
            caption = f"已记录 {len(candidates)} 个候选方案，{len(set(candidates))} 个不同目标值，接受 {accepted} 次。"
            if restarts is not None:
                caption += f"停滞后回到最优解 {restarts} 次。"
            st.caption(caption)
        st.write("")
        section_title("算子表现")
        st.plotly_chart(charts.operator_bars(result), use_container_width=True,
                        config={"displaylogo": False})
        if result.get("operator_stats"):
            st.caption("改进量记录算子产生新最优解时的目标值降低量；0 表示未调用或未产生改进。"
                       "破坏算子与修复算子的改进分别记录，不能简单相加为总改进。")
        else:
            st.caption("当前运行没有算子贡献记录。")

    with tab_gen:
        section_title("生成记录")
        if not ev:
            empty_state("暂无生成记录", "本次运行未写入 LLM 生成证据（可能未启用模型服务）。")
        else:
            rows = []
            for r in ev:
                sc = r.get("static_check") or {}
                ex = r.get("execution") or {}
                rows.append({
                    "记录时间": _fmt_ts(r.get("timestamp")),
                    "阶段": {"ui_run": "生成与求解"}.get(r.get("stage"), r.get("stage")),
                    "提示词编号": str(r.get("llm_prompt_hash") or "")[:12],
                    "静态检查": {True: "通过", False: "未通过"}.get(sc.get("passed"), "未执行"),
                    "算子来源": {
                        "llm_ok": "LLM 生成成功",
                        "not_configured": "未配置，使用预置算子",
                        "llm_error_fallback": "调用失败，使用预置算子",
                        "predefined_fallback": "检查未通过，使用预置算子",
                    }.get(r.get("recovery_action"), r.get("recovery_action")),
                    "求解目标值": ex.get("objective_value"),
                })
            try:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            except Exception:
                st.json(rows)
            with st.expander("查看原始生成代码", expanded=False):
                for r in ev:
                    code = r.get("generated_code")
                    if code:
                        st.code(code, language="python")

    with tab_export:
        _render_export(result, ev, run_id)


def _render_export(result, ev, run_id):
    section_title("当前运行导出")
    c1, c2, _ = st.columns([1.1, 1.1, 2])
    with c1:
        st.download_button(
            "导出当前结果 JSON",
            data=json.dumps(result, ensure_ascii=False, indent=2, default=str),
            file_name=f"{(run_id or 'result')}.json", mime="application/json",
            use_container_width=True, type="primary",
        )
    with c2:
        st.download_button(
            f"导出当前证据（{len(ev)} 条）",
            data=json.dumps(ev, ensure_ascii=False, indent=2, default=str),
            file_name=f"evidence_{run_id or 'current'}.json", mime="application/json",
            use_container_width=True, disabled=(len(ev) == 0),
        )

    st.write("")
    section_title("全部运行记录", "按运行时间倒序；可搜索实例名称或运行编号。")
    all_recs = _all_evidence()
    rows = _run_rows()
    if not rows:
        empty_state("暂无可导出的运行记录", "完成一次求解后这里会列出历史运行。")
        return

    q = st.text_input("搜索运行记录", placeholder="输入实例名称或运行编号片段",
                      label_visibility="collapsed")
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in str(r.get("运行名称", "")).lower()
                or ql in str(r.get("运行编号", "")).lower()]

    try:
        st.dataframe([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
                     use_container_width=True, hide_index=True)
    except Exception:
        st.json([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])

    st.download_button(
        f"导出全量证据 JSON（{len(all_recs)} 条）",
        data=json.dumps(all_recs, ensure_ascii=False, indent=2, default=str),
        file_name="evidence_all.json", mime="application/json",
        disabled=(len(all_recs) == 0),
    )
    with st.expander("开发详情", expanded=False):
        st.caption("本页对应原 T-15（可视化与证据导出）与 D5（平台证据记录）。"
                   "证据文件写入 evidence/rounds/<run_id>/iter_*.json。")
        st.write("- 证据根目录：`evidence/`")
        st.write("- 结果目录：`experiments/results/`")


def _all_evidence():
    recs = []
    for pat in [os.path.join(PROJECT_ROOT, "evidence", "iter_*.json"),
                os.path.join(PROJECT_ROOT, "evidence", "rounds", "**", "iter_*.json")]:
        for p in glob.glob(pat, recursive=True):
            try:
                with open(p, encoding="utf-8") as f:
                    obj = json.load(f)
                if isinstance(obj, dict):
                    recs.append(obj)
            except Exception:
                continue
    return recs
