"""ui/charts.py —— 统一图表：路径图（2D/3D）、收敛曲线、算子表现。

设计约束：
- 同一路径在 2D / 3D / 图例使用同一颜色（PATH_COLORS）。
- 去掉无分析意义的节点编号连续色条；节点用中性灰，路径用分类色。
- 图例置于绘图区外（顶部），不与色条/坐标轴重叠。
- 线宽 1.5–2px，节点小尺寸；tooltip 标明单位。
- 平直曲线如实显示，不伪造改进。
"""
from __future__ import annotations

from ui.styles import PATH_COLORS, TEXT, TEXT_MUTED, BORDER, PRIMARY

_FONT = "Segoe UI, Microsoft YaHei, PingFang SC, Roboto, Arial, sans-serif"
_NODE_GREY = "#AFB9C9"
_WAREHOUSE = "#182235"
_GRID = "#EDF1F8"


def _base_layout(fig, title: str, height: int = 460, showlegend: bool = True):
    fig.update_layout(
        template="plotly_white",
        title=dict(text=title, font=dict(size=15, color=TEXT, family=_FONT), x=0, xanchor="left"),
        height=height,
        margin=dict(l=64, r=24, t=64, b=48),
        font=dict(family=_FONT, size=12, color=TEXT_MUTED),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        showlegend=showlegend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    bgcolor="rgba(255,255,255,0.9)", bordercolor=BORDER, borderwidth=1,
                    font=dict(size=12, color=TEXT_MUTED)),
        hoverlabel=dict(font=dict(family=_FONT, size=12), bgcolor="#FFFFFF",
                        bordercolor=BORDER),
    )
    return fig


def _axes(fig):
    axis = dict(gridcolor=_GRID, zerolinecolor="#E1E7F0", linecolor=BORDER,
                tickfont=dict(size=10.5, color=TEXT_MUTED), showline=True)
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def path_map_2d(result: dict, inst: dict | None, height: int = 460):
    """经纬度坐标视图：客户节点 + 仓库 + 按路径着色的连线。"""
    import plotly.graph_objects as go

    fig = go.Figure()
    if not inst:
        return _base_layout(fig, "路径视图（缺少实例数据）", height, showlegend=False)

    nodes = inst.get("nodes") or []
    nmap = {}
    xs_all, ys_all = [], []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nmap[n.get("id")] = n
        xs_all.append(float(n.get("x", 0.0) or 0.0))
        ys_all.append(float(n.get("y", 0.0) or 0.0))

    # 全部客户节点（中性灰，降低常态视觉重量；密集时 hover 仍可查详情）
    if xs_all:
        fig.add_trace(go.Scatter(
            x=xs_all, y=ys_all, mode="markers", name="客户节点",
            marker=dict(size=3.5, color=_NODE_GREY, opacity=0.45,
                        line=dict(width=0)),
            hovertemplate="客户节点<br>经度 %{x:.6f}<br>纬度 %{y:.6f}<extra></extra>",
        ))

    # 各条路径
    paths = result.get("paths") or []
    for i, path in enumerate(paths):
        if not isinstance(path, list) or not path:
            continue
        color = PATH_COLORS[i % len(PATH_COLORS)]
        pxs, pys, ptext = [], [], []
        for nid in path:
            nd = nmap.get(nid)
            if nd is None:
                continue
            x = float(nd.get("x", 0.0) or 0.0)
            y = float(nd.get("y", 0.0) or 0.0)
            pxs.append(x)
            pys.append(y)
            role = "仓库" if nid == 0 else f"客户 {nid}"
            alt = nd.get("alt")
            alt_txt = f"<br>海拔 {float(alt):.1f} m" if alt is not None else ""
            ptext.append(f"{role}{alt_txt}<br>经度 {x:.6f}<br>纬度 {y:.6f}")
        if not pxs:
            continue
        fig.add_trace(go.Scatter(
            x=pxs, y=pys, mode="lines+markers", name=f"路径 {i + 1}",
            line=dict(color=color, width=1.8),
            marker=dict(size=5.5, color=color, line=dict(width=1, color="#FFFFFF")),
            text=ptext, hovertemplate="%{text}<extra>路径 " + str(i + 1) + "</extra>",
        ))

    # 仓库高亮
    depot = nmap.get(0)
    if depot is not None:
        fig.add_trace(go.Scatter(
            x=[float(depot.get("x", 0.0) or 0.0)],
            y=[float(depot.get("y", 0.0) or 0.0)],
            mode="markers", name="仓库",
            marker=dict(size=13, color=_WAREHOUSE, symbol="square",
                        line=dict(width=1.5, color="#FFFFFF")),
            hovertemplate="仓库<br>经度 %{x:.6f}<br>纬度 %{y:.6f}<extra></extra>",
        ))

    _base_layout(fig, "路径视图 · 经纬度坐标", height)
    _axes(fig)
    fig.update_xaxes(title_text="经度 (deg)", title_font=dict(size=12, color=TEXT_MUTED))
    fig.update_yaxes(title_text="纬度 (deg)", title_font=dict(size=12, color=TEXT_MUTED))
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def path_map_3d(result: dict, inst: dict | None, height: int = 560):
    """3D 空域视图：节点高度 + 按路径着色的航线。保留旋转/缩放/重置。"""
    import plotly.graph_objects as go

    fig = go.Figure()
    if not inst:
        return _base_layout(fig, "3D 空域视图（缺少实例数据）", height, showlegend=False)

    nodes = inst.get("nodes") or []
    nmap = {}
    for n in nodes:
        if isinstance(n, dict):
            nmap[n.get("id")] = n

    pts = [n for n in nodes if isinstance(n, dict)]
    if pts:
        fig.add_trace(go.Scatter3d(
            x=[float(n.get("x", 0.0) or 0.0) for n in pts],
            y=[float(n.get("y", 0.0) or 0.0) for n in pts],
            z=[float(n.get("alt", 0.0) or 0.0) for n in pts],
            mode="markers", name="客户节点",
            marker=dict(size=1.8, color=_NODE_GREY, opacity=0.38),
            hoverinfo="skip", showlegend=False,
        ))

    for i, path in enumerate(result.get("paths") or []):
        if not isinstance(path, list) or not path:
            continue
        color = PATH_COLORS[i % len(PATH_COLORS)]
        xs, ys, zs = [], [], []
        for nid in path:
            nd = nmap.get(nid)
            if nd is None:
                continue
            xs.append(float(nd.get("x", 0.0) or 0.0))
            ys.append(float(nd.get("y", 0.0) or 0.0))
            zs.append(float(nd.get("alt", 0.0) or 0.0))
        if not xs:
            continue
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs, mode="lines+markers", name=f"路径 {i + 1}",
            line=dict(color=color, width=3),
            marker=dict(size=3, color=color),
            hovertemplate="路径 " + str(i + 1) + "<br>经度 %{x:.6f}<br>纬度 %{y:.6f}"
                          "<br>海拔 %{z:.1f} m<extra></extra>",
        ))

    _base_layout(fig, "3D 空域视图 · 海拔与航线", height)
    axis3d = dict(
        gridcolor=_GRID, zerolinecolor="#E1E7F0", linecolor=BORDER,
        backgroundcolor="#FFFFFF", showbackground=True,
        tickfont=dict(size=10, color=TEXT_MUTED),
        title_font=dict(size=11, color=TEXT_MUTED),
    )
    fig.update_layout(scene=dict(
        xaxis=dict(title="经度 (deg)", **axis3d),
        yaxis=dict(title="纬度 (deg)", **axis3d),
        zaxis=dict(title="海拔 (m)", **axis3d),
        camera=dict(eye=dict(x=1.5, y=-1.5, z=1.1)),
    ))
    return fig


def convergence(history: list, height: int = 420, flat_note: bool = False):
    """收敛曲线：历史最优为主线，候选方案为次级（默认隐藏）。"""
    import plotly.graph_objects as go

    fig = go.Figure()
    hist = history or []
    if hist:
        iters = [h.get("iteration") for h in hist]
        best = [h.get("objective") for h in hist]
        fig.add_trace(go.Scatter(
            x=iters, y=best, mode="lines", name="历史最优目标值",
            line=dict(color=PRIMARY, width=2),
            hovertemplate="迭代 %{x}<br>历史最优 %{y:,.4f}<extra></extra>",
        ))
        cand = [(h.get("iteration"), h.get("candidate_objective"))
                for h in hist if h.get("candidate_objective") is not None]
        if cand:
            fig.add_trace(go.Scatter(
                x=[c[0] for c in cand], y=[c[1] for c in cand],
                mode="markers", name="候选方案目标值",
                marker=dict(size=4, color="#C2CBD9"),
                visible="legendonly",
                hovertemplate="迭代 %{x}<br>候选目标值 %{y:,.4f}<extra></extra>",
            ))
        vals = [v for v in best if v is not None]
        if vals and len(set(vals)) == 1:
            margin = max(abs(float(vals[0])) * 0.002, 1.0)
            fig.update_yaxes(range=[vals[0] - margin, vals[0] + margin])
    else:
        fig.add_annotation(text="当前运行没有保存迭代轨迹", showarrow=False,
                           font=dict(size=13, color=TEXT_MUTED), x=0.5, y=0.5,
                           xref="paper", yref="paper")

    _base_layout(fig, "搜索收敛过程", height)
    _axes(fig)
    fig.update_xaxes(title_text="迭代次数", title_font=dict(size=12, color=TEXT_MUTED))
    fig.update_yaxes(title_text="目标值（越低越好，元）",
                     title_font=dict(size=12, color=TEXT_MUTED), tickformat=",.0f")
    return fig


def operator_bars(result: dict, height: int = 420):
    """算子表现：横向条形图按目标值降低量排名。

    归因口径：破坏与修复算子的改进分别记录，不相加成总改进。
    """
    import plotly.graph_objects as go

    labels = {
        "random": "随机移除", "worst": "最差移除", "shaw": "相关移除",
        "relocate": "跨路径移动", "greedy": "贪心修复", "regret2": "Regret-2 修复",
        "llm": "LLM 生成算子",
    }
    stats = result.get("operator_stats") or {}
    fig = go.Figure()
    if stats:
        names = list(stats.keys())
        # 按改进量降序
        names.sort(key=lambda n: stats[n].get("improvement_total", 0.0), reverse=True)
        y = [labels.get(n, n) for n in names]
        gains = [stats[n].get("improvement_total", 0.0) for n in names]
        calls = [stats[n].get("calls", 0) for n in names]
        imps = [stats[n].get("improvements", 0) for n in names]
        colors = [PRIMARY if g > 0 else "#CFD7E4" for g in gains]
        fig.add_trace(go.Bar(
            x=gains, y=y, orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            customdata=list(zip(calls, imps)),
            hovertemplate="%{y}<br>调用 %{customdata[0]} 次"
                          "<br>产生新最优解 %{customdata[1]} 次"
                          "<br>目标值降低 %{x:,.4f}<extra></extra>",
            showlegend=False,
        ))
        top = max(gains) if gains else 0
        fig.update_xaxes(range=[0, max(top * 1.15, 1.0)])
    else:
        fig.add_annotation(text="当前运行没有算子贡献记录", showarrow=False,
                           font=dict(size=13, color=TEXT_MUTED), x=0.5, y=0.5,
                           xref="paper", yref="paper")

    _base_layout(fig, "算子表现 · 目标值降低量", height, showlegend=False)
    _axes(fig)
    fig.update_xaxes(title_text="目标值降低量（元）", title_font=dict(size=12, color=TEXT_MUTED))
    fig.update_yaxes(automargin=True)
    return fig
