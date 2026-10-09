"""ui/dashboard.py —— 四视图 + 证据导出（T-15 / FR-16 / D5）。

视图：
  1. 路径地图（plotly 散点：节点坐标 + 各子路径着色 + 仓库标记）
  2. 收敛曲线 + 算子热力图（目标值随迭代曲线；算子 results 热力）
  3. LLM 生成时间线（每轮 prompt_hash / 静态检查 / 恢复动作）
  4. 3D 空域视图（plotly 3D 散点：x/y/alt，高度着色）
导出：
  证据 JSON 下载（全量 + 按 run_id 过滤）
"""
from __future__ import annotations
import os
import json
import glob

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))


def _load_evidence() -> list:
    ev_dir = os.path.join(PROJECT_ROOT, "evidence")
    out = []
    for p in glob.glob(os.path.join(ev_dir, "iter_*.json")):
        try:
            out.append(json.load(open(p, encoding="utf-8")))
        except Exception:
            pass
    rounds_dir = os.path.join(ev_dir, "rounds")
    if os.path.isdir(rounds_dir):
        for rp in glob.glob(os.path.join(rounds_dir, "**", "iter_*.json"), recursive=True):
            try:
                out.append(json.load(open(rp, encoding="utf-8")))
            except Exception:
                pass
    out.sort(key=lambda r: r.get("iteration_id", 0))
    return out


def _load_latest_result() -> dict | None:
    res_dir = os.path.join(PROJECT_ROOT, "experiments", "results")
    files = sorted(glob.glob(os.path.join(res_dir, "A_*.json")) +
                   glob.glob(os.path.join(res_dir, "C_*.json")))
    if not files:
        return None
    return json.load(open(files[-1], encoding="utf-8"))


def _load_instance(instance_id: str) -> dict | None:
    p = os.path.join(PROJECT_ROOT, "data", "instances", f"{instance_id}.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return None


# ---- 视图 1：路径地图 ----
def _view_path_map(result: dict, inst: dict):
    import plotly.express as px
    import plotly.graph_objects as go
    fig = go.Figure()
    if inst:
        node_df = [(n["x"], n["y"], n["id"]) for n in inst.get("nodes", [])]
        trace = go.Scatter(
            x=[t[0] for t in node_df], y=[t[1] for t in node_df],
            mode="markers", marker=dict(size=4, color=[t[2] for t in node_df]),
            colorbar=dict(title="节点"), name="nodes",
        )
        fig.add_trace(trace)
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    for pi, path in enumerate(result.get("paths", [])[:5]):
        if not inst:
            continue
        nmap = {n["id"]: n for n in inst["nodes"]}
        nmap[0] = next((n for n in inst["nodes"] if n["id"] == 0), {"x": 0, "y": 0})
        xs = [nmap.get(i, {"x": 0})["x"] for i in path]
        ys = [nmap.get(i, {"y": 0})["y"] for i in path]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines+markers",
            line=dict(color=colors[pi % 5], width=2),
            marker=dict(size=8, color=colors[pi % 5]),
            name=f"Path {pi+1}",
        ))
    fig.update_layout(title="路径地图（子路径着色）", xaxis_title="Lon (deg)", yaxis_title="Lat (deg)")
    return fig


# ---- 视图 2：收敛曲线 + 算子热力 ----
def _view_convergence(recs: list, result: dict):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=2, cols=1,
                         subplot_titles=("目标值收敛曲线", "算子贡献热力"),
                         vertical_spacing=0.3)
    # 收敛曲线
    execs = [r for r in recs if r.get("execution", {}).get("objective_value") is not None]
    if execs:
        fig.add_trace(go.Scatter(
            x=[e.get("iteration_id") for e in execs],
            y=[e["execution"]["objective_value"] for e in execs],
            mode="lines+markers", name="objective",
        ), row=1, col=1)
    else:
        # 退用 result 的 iterations 占位
        if result.get("iterations"):
            fig.add_trace(go.Scatter(
                x=list(range(result["iterations"])),
                y=[result.get("objective_value")] * result["iterations"],
                mode="lines", name="objective (flat placeholder)",
            ), row=1, col=1)
    # 算子热力：从 result 的 operator_results
    op_res = result.get("operator_results")
    if op_res:
        names = list(op_res.keys())
        mat = [[op_res[n]] for n in names]
        fig.add_trace(go.Heatmap(z=mat, x=["contribution"], y=names), row=2, col=1)
    else:
        fig.add_trace(go.Scatter(x=[0], y=[0], mode="markers",
                                 text="无算子热力数据（请先跑 run_all.py 生成结果）"), row=2, col=1)
    fig.update_layout(height=600, title="收敛曲线与算子贡献")
    return fig


# ---- 视图 3：LLM 生成时间线 ----
def _view_llm_timeline(recs: list):
    import streamlit as st
    if not recs:
        st.info("暂无 LLM 时间线记录（未运行 LLM 生成或 evidence/ 为空）。")
        return
    st.dataframe({
        "iteration": [r.get("iteration_id") for r in recs],
        "stage": [r.get("stage") for r in recs],
        "prompt_hash": [r.get("llm_prompt_hash", "")[:12] for r in recs],
        "static_pass": [r.get("static_check", {}).get("passed") for r in recs],
        "recovery": [r.get("recovery_action") for r in recs],
        "objective": [r.get("execution", {}).get("objective_value") for r in recs],
    }, use_container_width=True)


# ---- 视图 4：3D 空域视图 ----
def _view_3d(instance: dict, result: dict):
    import plotly.express as px
    import plotly.graph_objects as go
    if not instance:
        return
    import pandas as pd
    df = pd.DataFrame(instance.get("nodes", []))
    if df.empty:
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter3d(
        x=df["x"], y=df["y"], z=df.get("alt", 0),
        mode="markers", marker=dict(size=3, color=df.get("alt", 0),
                                     colorscale="Viridis", showscale=True,
                                     colorbar=dict(title="Alt")),
    ))
    # 标注子路径
    for pi, path in enumerate(result.get("paths", [])[:3]):
        nmap = {n["id"]: n for n in instance["nodes"]}
        nmap[0] = next((n for n in instance["nodes"] if n["id"] == 0), {"x": 0, "y": 0, "alt": 0})
        fig.add_trace(go.Scatter3d(
            x=[nmap.get(i, {"x": 0})["x"] for i in path],
            y=[nmap.get(i, {"y": 0})["y"] for i in path],
            z=[nmap.get(i, {"alt": 0})["alt"] for i in path],
            mode="lines+markers", name=f"Path {pi+1}",
            line=dict(width=3),
        ))
    fig.update_layout(title="3D 空域视图（节点高度 + 子路径）",
                      scene=dict(xaxis_title="Lon", yaxis_title="Lat", zaxis_title="Alt"))
    return fig


# ---- 导出 ----
def _export_section(st):
    st.subheader("证据导出（D5）")
    ev_dir = os.path.join(PROJECT_ROOT, "evidence")
    files = glob.glob(os.path.join(ev_dir, "iter_*.json")) + \
            glob.glob(os.path.join(ev_dir, "rounds", "**", "iter_*.json"), recursive=True)
    if not files:
        st.warning("evidence/ 下暂无可导出的记录。")
        return
    # 全量导出
    all_recs = []
    for fp in files:
        try:
            all_recs.append(json.load(open(fp, encoding="utf-8")))
        except Exception:
            pass
    st.download_button(
        "导出全量证据 JSON",
        data=json.dumps(all_recs, ensure_ascii=False, indent=2),
        file_name="evidence_all.json",
        mime="application/json",
    )
    # 按 run_id 导出
    run_ids = sorted({r.get("run_id") or "default" for r in all_recs if isinstance(r, dict)})
    for rid in run_ids[:10]:
        subset = [r for r in all_recs if (r.get("run_id") or "default") == rid]
        st.download_button(
            f"导出 run={rid}（{len(subset)} 条）",
            data=json.dumps(subset, ensure_ascii=False, indent=2),
            file_name=f"evidence_{rid}.json",
            mime="application/json",
        )


def render_dashboard():
    import streamlit as st
    st.subheader("可视化四视图 + 证据导出（T-15）")
    recs = _load_evidence()
    result = _load_latest_result() or {}
    inst_id = result.get("instance_id", "")
    inst = _load_instance(inst_id) if inst_id else None
    if not inst:
        # 默认第一个实例
        inst_files = sorted(glob.glob(os.path.join(PROJECT_ROOT, "data", "instances", "*.json")))
        if inst_files:
            inst = json.load(open(inst_files[0], encoding="utf-8"))

    # 视图 1
    st.markdown("### 视图 1：路径地图")
    fig1 = _view_path_map(result, inst)
    if fig1:
        st.plotly_chart(fig1, use_container_width=True)
    else:
        st.info("请先在「求解」Tab 运行一次以生成路径结果。")

    # 视图 2
    st.markdown("### 视图 2：收敛曲线 + 算子热力")
    fig2 = _view_convergence(recs, result)
    st.plotly_chart(fig2, use_container_width=True)

    # 视图 3
    st.markdown("### 视图 3：LLM 生成时间线")
    _view_llm_timeline(recs)

    # 视图 4
    st.markdown("### 视图 4：3D 空域视图")
    if inst:
        fig4 = _view_3d(inst, result)
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("无实例数据。")

    # 导出
    st.markdown("### 证据导出")
    _export_section(st)
