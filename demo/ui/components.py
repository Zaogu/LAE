"""ui/components.py —— 复用组件：品牌标识、页头、面板、指标条、状态徽标、键值列表、空状态、图例。

均为纯展示组件，只读取真实数据；缺数据时走空状态分支，不编造数值。
"""
from __future__ import annotations

import html

from ui.styles import PATH_COLORS

# 品牌标识：路径节点 + 连线（几何线性）
BRAND_MARK = (
    '<svg class="mark" width="26" height="26" viewBox="0 0 26 26" fill="none" '
    'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<rect x="0.5" y="0.5" width="25" height="25" rx="6" fill="#EDF2FF" stroke="#C9D8FB"/>'
    '<path d="M7.5 18.5 L13 12.5 L18.5 7.5" stroke="#3659D9" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="7.5" cy="18.5" r="2.1" fill="#3659D9"/>'
    '<circle cx="13" cy="12.5" r="1.7" fill="#5B8FD6"/>'
    '<circle cx="18.5" cy="7.5" r="2.4" fill="#182235"/>'
    '</svg>'
)


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


def sidebar_brand() -> None:
    """侧边栏顶部品牌区：几何标识 + 产品名。"""
    import streamlit as st
    st.sidebar.markdown(
        f'<div class="app-sidebar-brand">{BRAND_MARK}'
        '<div><div class="brand-name">SDVRPD</div>'
        '<div class="brand-sub">路径优化工作台</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )


def page_head(title: str, subtitle: str = "") -> None:
    """页面标题区：H1 + 一句有用说明（不再重复技术副标题）。"""
    parts = [f'<div class="page-head"><h1>{_esc(title)}</h1>']
    if subtitle:
        parts.append(f'<div class="sub">{_esc(subtitle)}</div>')
    parts.append("</div>")
    import streamlit as st
    st.markdown("".join(parts), unsafe_allow_html=True)


def section_title(text: str, sub: str = "") -> None:
    import streamlit as st
    out = f'<div class="section-title">{_esc(text)}</div>'
    if sub:
        out += f'<div class="section-sub">{_esc(sub)}</div>'
    st.markdown(out, unsafe_allow_html=True)


def panel_label(text: str) -> None:
    """面板内的小标题。"""
    import streamlit as st
    st.markdown(f'<div class="panel-head">{_esc(text)}</div>', unsafe_allow_html=True)


def status_badge(state: str, text: str) -> str:
    """状态徽标 HTML。state ∈ {ok, warn, danger, idle, run}。"""
    cls = state if state in ("ok", "warn", "danger", "idle", "run") else "idle"
    return (f'<span class="status-badge {cls}"><span class="dot"></span>{_esc(text)}</span>')


def metric_row(items: list) -> None:
    """指标条。items: [(label, value, unit, state, lead), ...]
    state ∈ {"", "ok", "warn", "danger"}；lead=True 时作为视觉重点。
    value 为 str/int/float，None 显示 "—"。数字与单位保持同一行。
    """
    import streamlit as st
    cells = []
    for it in items:
        label = it[0]
        value = it[1]
        unit = it[2] if len(it) > 2 else ""
        state = it[3] if len(it) > 3 else ""
        lead = bool(it[4]) if len(it) > 4 else False
        vtxt = "—" if value is None else _esc(value)
        unit_html = f'<span class="unit">{_esc(unit)}</span>' if unit else ""
        cells.append(
            f'<div class="m{" lead" if lead else ""}"><div class="label">{_esc(label)}</div>'
            f'<div class="value {state}">{vtxt}{unit_html}</div></div>'
        )
    st.markdown(f'<div class="metric-row">{"".join(cells)}</div>', unsafe_allow_html=True)


def notice(text: str, kind: str = "") -> None:
    """紧凑辅助信息条。kind ∈ {"", "warn", "danger"}。"""
    import streamlit as st
    cls = f"notice {kind}" if kind in ("warn", "danger") else "notice"
    st.markdown(f'<div class="{cls}">{_esc(text)}</div>', unsafe_allow_html=True)


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
            f'<span>路径 {i + 1}</span><span class="cnt">{n} 客户</span></div>'
        )
    st.markdown(f'<div class="legend-list">{"".join(items)}</div>', unsafe_allow_html=True)
