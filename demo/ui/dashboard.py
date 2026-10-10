"""ui/dashboard.py — dashboard views and evidence export.

Views:
  1. Path map
  2. Convergence / operator heatmap
  3. LLM timeline
  4. 3D airspace view
"""
from __future__ import annotations
import glob
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))


def _safe_get(d, key, default=None):
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


def _load_evidence() -> list:
    ev_dir = os.path.join(PROJECT_ROOT, "evidence")
    out = []
    patterns = [
        os.path.join(ev_dir, "iter_*.json"),
        os.path.join(ev_dir, "rounds", "**", "iter_*.json"),
    ]
    for pat in patterns:
        for p in glob.glob(pat, recursive=True):
            try:
                with open(p, encoding="utf-8") as f:
                    obj = json.load(f)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    out.sort(key=lambda r: _safe_get(r, "iteration_id", 0) or 0)
    return out


def _load_latest_result() -> dict | None:
    res_dir = os.path.join(PROJECT_ROOT, "experiments", "results")
    # UI 求解会写固定指针，优先使用它；否则兼容命令行实验结果。
    files = [os.path.join(res_dir, "ui_last_result.json")]
    files += glob.glob(os.path.join(res_dir, "ui_*.json"))
    files += glob.glob(os.path.join(res_dir, "A_*.json"))
    files += glob.glob(os.path.join(res_dir, "C_*.json"))
    files = [p for p in files if os.path.isfile(p)]
    if not files:
        return None
    latest_ui = os.path.join(res_dir, "ui_last_result.json")
    ordered = sorted(set(files) - {latest_ui}, key=os.path.getmtime, reverse=True)
    if os.path.isfile(latest_ui):
        ordered.insert(0, latest_ui)
    for path in ordered:
        try:
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _filter_evidence_for_result(recs: list, result: dict) -> list:
    """避免旧运行的证据混进当前图表。旧证据没有 run_id 时保持兼容。"""
    run_id = _safe_get(result, "run_id")
    if not run_id:
        return recs
    return [r for r in recs if _safe_get(r, "run_id") == run_id]


def _load_instance(instance_id: str) -> dict | None:
    if not instance_id:
        return None
    p = os.path.join(PROJECT_ROOT, "data", "instances", f"{instance_id}.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _default_instance() -> dict | None:
    inst_files = sorted(glob.glob(os.path.join(PROJECT_ROOT, "data", "instances", "*.json")))
    for fp in inst_files:
        try:
            with open(fp, encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _node_map(inst: dict) -> dict:
    out = {}
    for n in _safe_get(inst, "nodes", []) or []:
        if isinstance(n, dict) and "id" in n:
            out[n["id"]] = n
    return out


def _view_path_map(result: dict, inst: dict | None):
    import plotly.graph_objects as go

    fig = go.Figure()
    if inst:
        nodes = _safe_get(inst, "nodes", []) or []
        pts = [(n.get("x", 0.0), n.get("y", 0.0), n.get("id")) for n in nodes if isinstance(n, dict)]
        if pts:
            trace = go.Scatter(
                x=[t[0] for t in pts],
                y=[t[1] for t in pts],
                mode="markers",
                marker=dict(size=4, color=[t[2] for t in pts], colorscale="Viridis", showscale=True),
                name="nodes",
            )
            trace.marker.colorbar = dict(title="node")
            fig.add_trace(trace)

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    if inst:
        nmap = _node_map(inst)
        nmap.setdefault(0, {"x": 0, "y": 0})
    for pi, path in enumerate(_safe_get(result, "paths", []) or []):
        if not isinstance(path, list):
            continue
        if not inst:
            continue
        nmap = _node_map(inst)
        nmap.setdefault(0, {"x": 0, "y": 0})
        xs, ys = [], []
        for node_id in path:
            nd = nmap.get(node_id, {"x": 0, "y": 0})
            xs.append(float(nd.get("x", 0) or 0))
            ys.append(float(nd.get("y", 0) or 0))
        if xs:
            fig.add_trace(go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                line=dict(color=colors[pi % 5], width=2),
                marker=dict(size=8, color=colors[pi % 5]),
                name=f"Path {pi + 1}",
            ))

    fig.update_layout(title="路径地图（子路径着色）", xaxis_title="Lon (deg)", yaxis_title="Lat (deg)")
    return fig


def _view_convergence(recs: list, result: dict):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    stats = _safe_get(result, "operator_stats", {}) or {}
    fig = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=("历史最优目标值", "算子改进记录" if stats else "算子反馈得分（旧版记录）"),
        vertical_spacing=0.22,
    )

    # 优先使用求解器逐迭代 history；旧版本没有 history 时才退回 evidence。
    history = _safe_get(result, "history", []) or []
    if history:
        fig.add_trace(go.Scatter(
            x=[h.get("iteration") for h in history],
            y=[h.get("objective") for h in history],
            mode="lines+markers",
            name="历史最优目标值",
            line=dict(color="#176B87", width=2),
            hovertemplate="迭代 %{x}<br>历史最优目标值 %{y:,.4f}<extra></extra>",
        ), row=1, col=1)
        candidates = [h for h in history if h.get("candidate_objective") is not None]
        if candidates:
            fig.add_trace(go.Scatter(
                x=[h["iteration"] for h in candidates],
                y=[h["candidate_objective"] for h in candidates],
                mode="lines+markers", name="候选方案目标值",
                line=dict(color="#999999", dash="dot"), visible="legendonly",
                hovertemplate="迭代 %{x}<br>候选方案目标值 %{y:,.4f}<extra></extra>",
            ), row=1, col=1)
        values = [h["objective"] for h in history if h.get("objective") is not None]
        if values and len(set(values)) == 1:
            margin = max(abs(float(values[0])) * 0.005, 1.0)
            fig.update_yaxes(range=[values[0] - margin, values[0] + margin], row=1, col=1)

    execs = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        exec_obj = _safe_get(r, "execution", {})
        if isinstance(exec_obj, dict) and exec_obj.get("objective_value") is not None:
            execs.append(r)

    if not history and execs:
        fig.add_trace(go.Scatter(
            x=[_safe_get(e, "iteration_id", None) for e in execs],
            y=[_safe_get(_safe_get(e, "execution", {}), "objective_value", None) for e in execs],
            mode="lines+markers",
            name="运行结果（缺少逐迭代轨迹）",
        ), row=1, col=1)
    elif not history:
        # 没有历史时显示明确状态，而不是伪造一条“平直收敛曲线”。
        fig.add_annotation(row=1, col=1, text="当前运行没有保存迭代轨迹", showarrow=False)

    labels = {
        "random": "随机移除", "worst": "最差移除", "shaw": "相关移除",
        "relocate": "跨路径移动", "greedy": "贪心修复", "regret2": "Regret-2 修复",
        "llm": "AI 生成算子",
    }
    op_res = _safe_get(result, "operator_results", None) or _safe_get(result, "results", None)
    if stats:
        names = list(stats)
        gains = [[stats[n].get("improvement_total", 0.0)] for n in names]
        details = [[[stats[n].get("calls", 0), stats[n].get("improvements", 0)]] for n in names]
        fig.add_trace(go.Heatmap(
            z=gains, x=["目标值降低量"], y=[labels.get(n, n) for n in names],
            customdata=details, colorscale="Blues", zmin=0,
            zmax=max(1.0, max(v[0] for v in gains)),
            colorbar=dict(title="改进量", len=0.38, y=0.19),
            hovertemplate="%{y}<br>调用 %{customdata[0]} 次<br>产生新最优解 %{customdata[1]} 次"
                          "<br>目标值降低 %{z:,.4f}<extra></extra>",
        ), row=2, col=1)
    elif op_res and isinstance(op_res, dict):
        names = list(op_res.keys())
        mat = [[op_res[n]] for n in names]
        fig.add_trace(go.Heatmap(
            z=mat, x=["反馈得分"], y=[labels.get(n, n) for n in names],
            colorscale="Blues", colorbar=dict(title="得分", len=0.38, y=0.19),
        ), row=2, col=1)
    else:
        fig.add_annotation(row=2, col=1, text="当前运行没有算子贡献记录", showarrow=False)

    fig.update_xaxes(title_text="迭代次数", dtick=1 if len(history) <= 20 else None, row=1, col=1)
    fig.update_yaxes(title_text="目标值（越低越好）", tickformat=",.2f", row=1, col=1)
    fig.update_layout(height=680, title="搜索过程与算子表现", template="plotly_white",
                      legend=dict(orientation="h", y=1.08), margin=dict(t=100, b=50))
    return fig


def _view_llm_timeline(recs: list):
    import streamlit as st

    if not recs:
        st.info("暂无 LLM 时间线记录（evidence/ 为空或尚未生成证据）。")
        return

    rows = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        static_check = _safe_get(r, "static_check", {})
        execution = _safe_get(r, "execution", {})
        prompt_hash = _safe_get(r, "llm_prompt_hash", "") or ""
        rows.append({
            "记录时间": _safe_get(r, "timestamp"),
            "记录阶段": "生成与求解" if r.get("stage") == "ui_run" else r.get("stage"),
            "提示词编号": str(prompt_hash)[:12],
            "静态检查": {True: "通过", False: "未通过"}.get(_safe_get(static_check, "passed"), "未执行"),
            "AI 状态": {
                "llm_ok": "生成成功", "not_configured": "未配置，使用预置算子",
                "llm_error_fallback": "调用失败，使用预置算子",
                "predefined_fallback": "检查失败，使用预置算子",
            }.get(r.get("recovery_action"), r.get("recovery_action")),
            "求解目标值": _safe_get(execution, "objective_value"),
        })
    if not rows:
        st.info("evidence 记录中未解析到有效行。")
        return
    # Streamlit 的 dataframe 依赖 pyarrow；部分旧环境中 pyarrow 与项目的
    # NumPy 1.x 版本不兼容。时间线本身是诊断信息，降级为 JSON 仍保留全部内容。
    try:
        st.dataframe(rows, use_container_width=True)
    except (ImportError, ModuleNotFoundError):
        st.info("当前环境的表格依赖不可用，以下为同一份时间线数据：")
        st.json(rows)


def _view_3d(instance: dict | None, result: dict):
    import plotly.graph_objects as go

    if not instance:
        return None

    nodes = _safe_get(instance, "nodes", []) or []
    if not nodes:
        return None

    xs, ys, zs = [], [], []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        xs.append(float(n.get("x", 0.0) or 0.0))
        ys.append(float(n.get("y", 0.0) or 0.0))
        zs.append(float(n.get("alt", 0.0) or 0.0))

    if not xs:
        return None

    fig = go.Figure()
    node_trace = go.Scatter3d(
        x=xs,
        y=ys,
        z=zs,
        mode="markers",
        marker=dict(size=3, color=zs, colorscale="Viridis", showscale=True),
    )
    node_trace.marker.colorbar = dict(title="Alt")
    fig.add_trace(node_trace)

    nmap = _node_map(instance)
    nmap.setdefault(0, {"x": 0, "y": 0, "alt": 0})
    for pi, path in enumerate(_safe_get(result, "paths", []) or []):
        if not isinstance(path, list):
            continue
        xs3, ys3, zs3 = [], [], []
        for node_id in path:
            nd = nmap.get(node_id, {"x": 0, "y": 0, "alt": 0})
            xs3.append(float(nd.get("x", 0) or 0.0))
            ys3.append(float(nd.get("y", 0) or 0.0))
            zs3.append(float(nd.get("alt", 0) or 0.0))
        if xs3:
            fig.add_trace(go.Scatter3d(
                x=xs3,
                y=ys3,
                z=zs3,
                mode="lines+markers",
                name=f"Path {pi + 1}",
                line=dict(width=3),
            ))

    fig.update_layout(
        title="3D 空域视图（节点高度 + 子路径）",
        scene=dict(xaxis_title="Lon", yaxis_title="Lat", zaxis_title="Alt"),
    )
    return fig


def _export_section(st):
    st.subheader("证据导出（D5）")
    ev_dir = os.path.join(PROJECT_ROOT, "evidence")
    files = (
        glob.glob(os.path.join(ev_dir, "iter_*.json"))
        + glob.glob(os.path.join(ev_dir, "rounds", "**", "iter_*.json"), recursive=True)
    )
    if not files:
        st.warning("evidence/ 下暂无可导出的记录。")
        return

    all_recs = []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                obj = json.load(f)
            if isinstance(obj, dict):
                all_recs.append(obj)
        except Exception:
            continue

    if not all_recs:
        st.warning("evidence/ 中有文件，但未解析到有效 JSON 记录。")
        return

    st.download_button(
        "导出全量证据 JSON",
        data=json.dumps(all_recs, ensure_ascii=False, indent=2, default=str),
        file_name="evidence_all.json",
        mime="application/json",
    )

    run_ids = sorted({str(_safe_get(r, "run_id") or "default") for r in all_recs})
    for rid in run_ids[:10]:
        subset = [r for r in all_recs if str(_safe_get(r, "run_id") or "default") == rid]
        st.download_button(
            f"导出 run={rid}（{len(subset)} 条）",
            data=json.dumps(subset, ensure_ascii=False, indent=2, default=str),
            file_name=f"evidence_{rid}.json",
            mime="application/json",
        )


def render_dashboard():
    import streamlit as st

    st.subheader("可视化四视图 + 证据导出（T-15）")
    recs = _load_evidence()
    result = _load_latest_result() or {}
    recs = _filter_evidence_for_result(recs, result)
    inst_id = _safe_get(result, "instance_id", "")
    inst = _load_instance(inst_id) if inst_id else None
    if not inst:
        inst = _default_instance()

    if result:
        st.caption(f"当前结果：{_safe_get(result, 'instance_name', _safe_get(result, 'instance_id', '未知实例'))} | 运行编号：{_safe_get(result, 'run_id', '历史结果')}")
        if inst:
            from solver.model import validate_routes
            validation = validate_routes(result.get("paths"), result.get("unassigned"), inst)
            if not validation["passed"]:
                st.error("当前保存结果未通过路线完整性检查：" + "；".join(validation["errors"]) +
                         "。图中的目标值来自原记录，不能作为可行方案的成本，请在求解页重新运行。")
        if result.get("invalid_candidates"):
            st.info(f"本次拦截 {result['invalid_candidates']} 个不可行候选方案，最终结果只保留通过检查的路线。")
    else:
        st.warning("尚未找到求解结果，请先在“求解”页运行一个实例。")

    st.markdown("### 视图 1：路径地图")
    fig1 = _view_path_map(result, inst)
    st.plotly_chart(fig1, use_container_width=True)

    st.markdown("### 视图 2：收敛曲线 + 算子热力")
    fig2 = _view_convergence(recs, result)
    st.plotly_chart(fig2, use_container_width=True)
    history = result.get("history") or []
    values = [h["objective"] for h in history if h.get("objective") is not None]
    if values and len(set(values)) == 1:
        st.info(f"本次完成 {result.get('iterations', 0)} 次迭代，尚未找到更优解，因此历史最优曲线保持平直。"
                "可点击图例中的“候选方案目标值”，查看实际尝试过的方案。")
    if result.get("operator_stats"):
        st.caption("改进量记录实际执行的算子产生新最优解时的目标值降低量；0 可能表示未调用或未产生改进。"
                   "破坏和修复算子共同完成的改进分别记录，不能将两者相加作为总改进。")
    elif result.get("operator_results"):
        st.caption("这是旧版反馈得分：产生新最优解加 2 分，其他尝试加 0.1 分，并不等于成本降低量。"
                   "重新运行后会保存准确的算子调用和改进记录。")

    st.markdown("### 视图 3：LLM 生成时间线")
    _view_llm_timeline(recs)

    st.markdown("### 视图 4：3D 空域视图")
    if inst:
        fig4 = _view_3d(inst, result)
        if fig4:
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("3D 视图缺少节点坐标或高度字段。")
    else:
        st.info("无实例数据。")

    st.markdown("### 证据导出")
    _export_section(st)
