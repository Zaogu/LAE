"""ui/theme.py —— 科研主题：深色夜空背景 + 统一配色 + 卡片布局。

注入一次即可生效（在 app.py 顶部调用 apply_theme()）。
仅负责 Streamlit 外观，不涉及任何求解逻辑。

设计语言（无人机航路网 / 空域感知意象）：
  - 底色：深蓝夜空 #0d1b2a
  - 主色：航路青 #48cae4 / 高光 #90e0ef
  - 辅色：暖橙 #f4a261（强调）
  - 卡片：半透明深蓝 + 细边框 + 圆角
  - 背景：经纬网格 + 星点 + 柔光晕
"""
from __future__ import annotations

import streamlit as st

THEME_CSS = """
<style>
/* ---------- 全局背景：深蓝夜空 + 经纬网格 + 星点 + 柔光 ---------- */
.stApp {
    background-color: #0a1420;
}
[data-testid="stMainContainer"] {
    background:
        radial-gradient(circle at 20% 20%, rgba(72, 202, 228, 0.10), transparent 45%),
        radial-gradient(circle at 80% 10%, rgba(144, 224, 239, 0.08), transparent 40%),
        radial-gradient(circle at 60% 90%, rgba(244, 162, 97, 0.06), transparent 50%),
        linear-gradient(180deg, #0a1420 0%, #0d1b2a 100%);
    background-size: cover;
}
/* 经纬网格层：用 repeating 网格模拟航路坐标网 */
[data-testid="stMainContainer"]::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background-image:
        linear-gradient(rgba(72, 202, 228, 0.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(72, 202, 228, 0.06) 1px, transparent 1px);
    background-size: 48px 48px;
    opacity: 0.5;
    z-index: 0;
}
[data-testid="stMainBlockContainer"] { position: relative; z-index: 1; }

/* ---------- 文字色 ---------- */
.stApp, [data-testid="stMainContainer"] { color: #e6edf5; }
h1, h2, h3, h4 { color: #90e0ef; font-weight: 600; letter-spacing: .2px; }
.stMarkdown p, .stCaption, .stMarkdown li { color: #cbd5e1; }

/* ---------- 侧边栏：深玻璃卡片 ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(13,27,42,0.92), rgba(10,20,32,0.95));
    border-right: 1px solid rgba(72,202,228,0.15);
    backdrop-filter: blur(6px);
}
[data-testid="stSidebar"] .stRadio label { color: #cbd5e1; }

/* ---------- 卡片：分区容器（.sci-card） ---------- */
.sci-card {
    background: rgba(13, 27, 42, 0.62);
    border: 1px solid rgba(72, 202, 228, 0.18);
    border-radius: 14px;
    padding: 18px 22px;
    margin: 14px 0;
    box-shadow: 0 6px 24px rgba(0,0,0,0.35);
    backdrop-filter: blur(4px);
}
.sci-card .sci-title {
    color: #48cae4;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px dashed rgba(72,202,228,0.25);
    display: flex; align-items: center; gap: 8px;
}
.sci-card .sci-title::before {
    content: "";
    width: 8px; height: 8px; border-radius: 50%;
    background: #48cae4; box-shadow: 0 0 8px #48cae4;
}

/* ---------- KPI 指标行 ---------- */
.sci-kpi {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
}
.sci-kpi .kpi {
    background: rgba(72, 202, 228, 0.07);
    border: 1px solid rgba(72, 202, 228, 0.18);
    border-radius: 10px;
    padding: 12px 14px;
    text-align: center;
}
.sci-kpi .kpi .kpi-val {
    font-family: "SF Mono", "Cascadia Code", Consolas, monospace;
    font-size: 22px; font-weight: 700; color: #90e0ef;
}
.sci-kpi .kpi .kpi-val.ok   { color: #52d08a; }
.sci-kpi .kpi .kpi-val.warn { color: #f4a261; }
.sci-kpi .kpi .kpi-label {
    font-size: 11px; color: #7f95a8; letter-spacing: 1px;
    text-transform: uppercase; margin-top: 4px;
}

/* ---------- Streamlit 原生元素配色覆盖 ---------- */
.stButton > button {
    background: linear-gradient(90deg, #48cae4, #1f6f8b);
    color: #06121c; font-weight: 600;
    border: none; border-radius: 8px;
    transition: all .18s;
}
.stButton > button:hover { filter: brightness(1.12); transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(72,202,228,0.4); }
[data-testid="stFormSubmit"] > button {
    background: linear-gradient(90deg, #48cae4, #1f6f8b);
    color: #06121c; font-weight: 600;
}

/* 表单与输入 */
[data-baseweb="text-input"] input,
[data-baseweb="number-input"] input {
    background: rgba(10, 20, 32, 0.7) !important;
    color: #e6edf5 !important;
    border: 1px solid rgba(72,202,228,0.25) !important;
    border-radius: 8px;
}
[data-baseweb="select"] > div {
    background: rgba(10, 20, 32, 0.7);
    color: #e6edf5; border-radius: 8px;
}
[data-baseweb="slider"] { color: #cbd5e1; }

/* alert 框 */
[data-testid="stSuccess"] {
    background: rgba(82, 208, 138, 0.10);
    border: 1px solid rgba(82, 208, 138, 0.35); color: #a3e9c4;
}
[data-testid="stError"] {
    background: rgba(239, 90, 90, 0.10);
    border: 1px solid rgba(239, 90, 90, 0.35); color: #fca5a5;
}
[data-testid="stInfo"] {
    background: rgba(72, 202, 228, 0.08);
    border: 1px solid rgba(72, 202, 228, 0.30); color: #90e0ef;
}
[data-testid="stWarning"] {
    background: rgba(244, 162, 97, 0.10);
    border: 1px solid rgba(244, 162, 97, 0.35); color: #f4c497;
}

/* 代码 / JSON 块 */
pre, code { background: rgba(10, 20, 32, 0.8) !important; color: #90e0ef;
    border-radius: 8px; }
[stTheme] { --primaryColor: #48cae4; --backgroundColor: #0d1b2a;
    --secondaryBackgroundColor: #13283a; --textColor: #e6edf5;
    --fontFamily: "Segoe UI", system-ui, sans-serif; }

/* dataframe */
[data-testid="stDataFrame"] {
    background: rgba(10,20,32,0.5);
    border-radius: 10px;
}
/* tabs */
[role="tablist"] [role="tab"] { border-bottom: 2px solid transparent; }
[role="tablist"] [aria-selected="true"] {
    border-bottom: 2px solid #48cae4; color: #48cae4;
}
</style>
"""


def apply_theme() -> None:
    """注入整套主题（背景 + 配色 + 卡片 + 原生元素覆盖）。"""
    st.set_page_config(
        page_title="SDVRPD LLM ALNS · 科研求解台",
        page_icon="🚁",
        layout="wide",
    )
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def card(title: str, body_fn) -> None:
    """渲染一个 .sci-card 分区；body_fn(st) 在卡片内部绘制内容。"""
    st.markdown(f'<div class="sci-card"><div class="sci-title">{title}</div>',
                unsafe_allow_html=True)
    body_fn(st)
    st.markdown("</div>", unsafe_allow_html=True)


def kpi_row(items: list) -> None:
    """渲染 KPI 指标行。items: [(label, value, status), ...]，status ∈ {ok,warn,info}。"""
    cells = []
    for label, value, status in items:
        cls = {"ok": "ok", "warn": "warn"}.get(status, "")
        cells.append(
            f'<div class="kpi"><div class="kpi-val {cls}">{value}</div>'
            f'<div class="kpi-label">{label}</div></div>'
        )
    st.markdown(f'<div class="sci-kpi">{"".join(cells)}</div>',
                unsafe_allow_html=True)
