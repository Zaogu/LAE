"""ui/components.py —— 复用组件：页头、指标行、状态徽标、键值列表、空状态、图例。

均为纯展示组件，只读取真实数据；缺数据时走空状态分支，不编造数值。
"""
from __future__ import annotations

import html

from ui.styles import PATH_COLORS


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


def sidebar_brand() -> None:
    """侧边栏顶部产品名。"""
    import streamlit as st
    st.sidebar.markdown(
        '<div class="app-sidebar-brand">'
        '<div class="brand-name">SDVRPD</div>'
        '<div class="brand-sub">路径优化工作台</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def page_head(title: str, subtitle: str = "", tech: str = "") -> None:
    """页面标题区：H1 + 次级说明 + 技术全称（小字，不抢视线）。"""
    parts = [f'<div class="page-head"><h1>{_esc(title)}</h1>']
    if subtitle:
        parts.append(f'<div class="sub">{_esc(subtitle)}</div>')
    if tech:
        parts.append(f'<div class="tech">{_esc(tech)}</div>')
    parts.append("</div>")
    import streamlit as st
    st.markdown("".join(parts), unsafe_allow_html=True)


def section_title(text: str, sub: str = "") -> None:
    import streamlit as st
    out = f'<div class="section-title">{_esc(text)}</div>'
    if sub:
        out += f'<div class="section-sub">{_esc(sub)}</div>'
    st.markdown(out, unsafe_allow_html=True)


def status_badge(state: str, text: str) -> str:
    """返回状态徽标 HTML。state ∈ {ok, warn, danger, idle, run}。"""
    cls = state if state in ("ok", "warn", "danger", "idle", "run") else "idle"
    return (f'<span class="status-badge {cls}"><span class="dot"></span>{_esc(text)}</span>')


def metric_row(items: list) -> None:
    """指标行。items: [(label, value, unit, state), ...]
    state ∈ {"", "ok", "warn", "danger"}；value 为 str/int/float，None 显示 "—"。
    """
    import streamlit as st
    cells = []
    for it in items:
        label = it[0]
        value = it[1]
        unit = it[2] if len(it) > 2 else ""
        state = it[3] if len(it) > 3 else ""
        vtxt = "—" if value is None else _esc(value)
        unit_html = f'<span class="unit">{_esc(unit)}</span>' if unit else ""
        cells.append(
            f'<div class="m"><div class="label">{_esc(label)}</div>'
            f'<div class="value {state}">{vtxt}{unit_html}</div></div>'
        )
    st.markdown(f'<div class="metric-row">{"".join(cells)}</div>', unsafe_allow_html=True)


def kv_list(rows: list) -> None:
    """键值描述列表。rows: [(key, value, mono_bool), ...]；value None 显示 "—"。"""
    import streamlit as st
    out = ['<div class="kv">']
    for r in rows:
        k, v = r[0], r[1]
        mono = r[2] if len(r) > 2 else False
        vtxt = "—" if v in (None, "") else _esc(v)
        cls = "v mono" if mono else "v"
        out.append(f'<div class="row"><span class="k">{_esc(k)}</span>'
                   f'<span class="{cls}">{vtxt}</span></div>')
    out.append("</div>")
    st.markdown("".join(out), unsafe_allow_html=True)


def empty_state(title: str, desc: str = "") -> None:
    import streamlit as st
    st.markdown(
        f'<div class="empty-state"><div class="es-title">{_esc(title)}</div>'
        f'<div class="es-desc">{_esc(desc)}</div></div>',
        unsafe_allow_html=True,
    )


def path_legend(paths: list) -> None:
    """路径图例：与 2D/3D 图共用 PATH_COLORS 的同一套颜色。"""
    import streamlit as st
    items = []
    for i, p in enumerate(paths or []):
        color = PATH_COLORS[i % len(PATH_COLORS)]
        n = len([x for x in p if x != 0]) if isinstance(p, list) else 0
        items.append(
            f'<div class="item"><span class="swatch" style="background:{color}"></span>'
            f'<span>路径 {i + 1}</span><span class="cnt">{n} 个客户</span></div>'
        )
    st.markdown(f'<div class="legend-list">{"".join(items)}</div>', unsafe_allow_html=True)
