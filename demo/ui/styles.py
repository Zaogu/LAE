"""ui/styles.py —— 设计令牌与全局样式（浅色工程工作台）。

只使用 Streamlit 官方稳定的 data-testid 属性（stApp / stSidebar / stMetric 等），
不依赖易失效的内部 DOM 层级选择器。

色板（浅色工程工作台）
  背景 #F7F8FA · 表面 #FFFFFF · 主文字 #20242C · 次级文字 #626B78 · 边框 #E3E7ED
  主操作 #315EFB · 成功 #1A7F4B · 提醒 #B7791F · 错误 #C0392B
"""
from __future__ import annotations

# ---- 设计令牌 --------------------------------------------------------------
BG = "#F7F8FA"
SURFACE = "#FFFFFF"
TEXT = "#20242C"
TEXT_MUTED = "#626B78"
TEXT_FAINT = "#8A93A0"
BORDER = "#E3E7ED"
BORDER_STRONG = "#CFD6E0"
PRIMARY = "#315EFB"
PRIMARY_DARK = "#2447C9"
SUCCESS = "#1A7F4B"
WARN = "#B7791F"
DANGER = "#C0392B"

# 路径分类配色（跨 2D / 3D / 图例 / 表格保持一致）
PATH_COLORS = [
    "#315EFB",  # 蓝（主）
    "#E4572E",  # 橙红
    "#1A7F4B",  # 绿
    "#8E44AD",  # 紫
    "#0E8A8A",  # 青
    "#B7791F",  # 琥珀
    "#C0392B",  # 红
    "#5B6BB5",  # 靛
]

FONT_STACK = ('-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", '
              '"PingFang SC", "Hiragino Sans GB", Roboto, "Helvetica Neue", Arial, sans-serif')
MONO_STACK = ('"Cascadia Code", "SF Mono", Consolas, "Liberation Mono", Menlo, monospace')

CSS = """
<style>
:root {
  --bg: #F7F8FA;
  --surface: #FFFFFF;
  --text: #20242C;
  --text-muted: #626B78;
  --text-faint: #8A93A0;
  --border: #E3E7ED;
  --border-strong: #CFD6E0;
  --primary: #315EFB;
  --primary-dark: #2447C9;
  --success: #1A7F4B;
  --warn: #B7791F;
  --danger: #C0392B;
  --mono: "Cascadia Code", "SF Mono", Consolas, "Liberation Mono", Menlo, monospace;
}

html, body, .stApp { background: var(--bg); }
.stApp, .stMarkdown, .stMarkdown p, label, .stCaption { color: var(--text); }
body, .stApp { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei",
  "PingFang SC", "Hiragino Sans GB", Roboto, "Helvetica Neue", Arial, sans-serif; }

/* 主内容区留白：桌面 32px，窄屏自适应 */
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 100%; }
@media (min-width: 1100px) { .block-container { padding-left: 2rem; padding-right: 2rem; } }

/* 去掉 Streamlit 顶部默认留白与装饰条 */
header[data-testid="stHeader"] { background: transparent; height: 0; }
[data-testid="stToolbar"] { display: none; }
[data-testid="stDecoration"] { display: none; }

/* ---- 侧边栏 ---- */
[data-testid="stSidebar"] {
  background: var(--surface);
  border-right: 1px solid var(--border);
  width: 224px !important; min-width: 224px !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1.1rem; }
[data-testid="stSidebar"] .stRadio > label { display: none; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] { gap: 2px; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label {
  display: flex; align-items: center;
  padding: 7px 10px; margin: 0; border-radius: 6px;
  border: 1px solid transparent; cursor: pointer;
  transition: background .12s, border-color .12s;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:hover {
  background: #F1F3F7;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label > div:first-child {
  display: none;  /* 隐藏原生圆点，用背景表达选中 */
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label[data-checked="true"],
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(input:checked) {
  background: #EDF1FE; border-color: #C9D6FD;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label p {
  font-size: 14px; color: var(--text); font-weight: 500; margin: 0;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(input:checked) p {
  color: var(--primary-dark); font-weight: 600;
}

/* ---- 页头（产品名/页面名） ---- */
.app-sidebar-brand { padding: 2px 10px 14px 10px; border-bottom: 1px solid var(--border);
  margin-bottom: 10px; }
.app-sidebar-brand .brand-name { font-size: 16px; font-weight: 700; letter-spacing: .3px;
  color: var(--text); }
.app-sidebar-brand .brand-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

.page-head { margin: 0 0 18px 0; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
.page-head h1 { font-size: 25px; font-weight: 650; color: var(--text); margin: 0; line-height: 1.25;
  letter-spacing: -.2px; }
.page-head .sub { font-size: 13px; color: var(--text-muted); margin-top: 5px; line-height: 1.5; }
.page-head .tech { font-size: 12px; color: var(--text-faint); margin-top: 4px; }

/* ---- 小节标题 ---- */
.section-title { font-size: 16px; font-weight: 600; color: var(--text); margin: 4px 0 10px 0;
  letter-spacing: -.1px; }
.section-sub { font-size: 13px; color: var(--text-muted); margin: -6px 0 12px 0; line-height: 1.55; }

/* ---- 指标行 ---- */
.metric-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 8px;
  overflow: hidden; }
.metric-row .m { background: var(--surface); padding: 12px 16px; }
.metric-row .m .label { font-size: 12px; color: var(--text-muted); margin-bottom: 4px;
  letter-spacing: .2px; }
.metric-row .m .value { font-size: 20px; font-weight: 620; color: var(--text);
  font-family: var(--mono); font-variant-numeric: tabular-nums; line-height: 1.2; }
.metric-row .m .value .unit { font-size: 12px; color: var(--text-faint); font-weight: 400;
  margin-left: 3px; font-family: inherit; }
.metric-row .m .value.ok { color: var(--success); }
.metric-row .m .value.warn { color: var(--warn); }
.metric-row .m .value.danger { color: var(--danger); }

/* ---- 状态徽标 ---- */
.status-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px;
  font-weight: 550; padding: 3px 10px; border-radius: 999px; border: 1px solid; line-height: 1.6; }
.status-badge .dot { width: 7px; height: 7px; border-radius: 50%; }
.status-badge.ok { color: var(--success); background: #EEF8F2; border-color: #C7E7D5; }
.status-badge.ok .dot { background: var(--success); }
.status-badge.warn { color: var(--warn); background: #FDF6E9; border-color: #EEDCB4; }
.status-badge.warn .dot { background: var(--warn); }
.status-badge.danger { color: var(--danger); background: #FCEEEC; border-color: #F0C8C1; }
.status-badge.danger .dot { background: var(--danger); }
.status-badge.idle { color: var(--text-muted); background: #F1F3F7; border-color: var(--border-strong); }
.status-badge.idle .dot { background: var(--text-faint); }
.status-badge.run { color: var(--primary-dark); background: #EDF1FE; border-color: #C9D6FD; }
.status-badge.run .dot { background: var(--primary); animation: pulse 1.1s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

/* ---- 描述型列表（键值对） ---- */
.kv { border: 1px solid var(--border); border-radius: 8px; background: var(--surface);
  overflow: hidden; }
.kv .row { display: flex; justify-content: space-between; align-items: baseline; gap: 16px;
  padding: 9px 14px; border-bottom: 1px solid var(--border); }
.kv .row:last-child { border-bottom: none; }
.kv .row .k { font-size: 13px; color: var(--text-muted); flex: 0 0 auto; }
.kv .row .v { font-size: 13px; color: var(--text); text-align: right; word-break: break-word;
  min-width: 0; }
.kv .row .v.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }

/* ---- 空状态 ---- */
.empty-state { border: 1px dashed var(--border-strong); border-radius: 8px;
  background: var(--surface); padding: 26px 22px; text-align: center; }
.empty-state .es-title { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 5px; }
.empty-state .es-desc { font-size: 13px; color: var(--text-muted); line-height: 1.6; }

/* ---- 路径图例 ---- */
.legend-list { display: flex; flex-direction: column; gap: 6px; }
.legend-list .item { display: flex; align-items: center; gap: 8px; font-size: 13px;
  color: var(--text); }
.legend-list .item .swatch { width: 12px; height: 12px; border-radius: 3px; flex: 0 0 auto; }
.legend-list .item .cnt { margin-left: auto; color: var(--text-muted); font-family: var(--mono);
  font-size: 12px; font-variant-numeric: tabular-nums; }

/* ---- 控件 ---- */
.stButton > button {
  border-radius: 7px; border: 1px solid var(--border-strong); background: var(--surface);
  color: var(--text); font-weight: 550; font-size: 14px; height: 38px; transition: all .12s;
}
.stButton > button:hover { border-color: var(--primary); color: var(--primary-dark);
  background: #F6F8FF; }
.stButton > button:focus-visible { outline: 2px solid var(--primary); outline-offset: 1px; }
.stButton > button[kind="primary"], .stButton > button[data-testid="baseButton-primary"] {
  background: var(--primary); border-color: var(--primary); color: #fff;
}
.stButton > button[kind="primary"]:hover { background: var(--primary-dark);
  border-color: var(--primary-dark); color: #fff; }
.stDownloadButton > button {
  border-radius: 7px; border: 1px solid var(--border-strong); background: var(--surface);
  color: var(--text); font-size: 13px; height: 36px;
}
.stDownloadButton > button:hover { border-color: var(--primary); color: var(--primary-dark); }

[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="base-input"] {
  border-radius: 7px !important;
}
input, .stTextInput input, .stNumberInput input { color: var(--text) !important; }
[data-baseweb="input"] { border-color: var(--border-strong) !important; }
[data-testid="stMetricValue"] { font-family: var(--mono); font-variant-numeric: tabular-nums; }

/* tabs */
[data-testid="stTabs"] button[role="tab"] { font-size: 14px; font-weight: 550;
  color: var(--text-muted); }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color: var(--primary-dark); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: var(--primary); }
[data-testid="stTabs"] [data-baseweb="tab-border"] { background: var(--border); }

/* 表格 */
[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 8px; }

/* 容器边框（st.container(border=True)） */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 8px; }
hr { border-color: var(--border); }
</style>
"""


def inject() -> None:
    """注入全局样式（每个页面调用一次，位于 set_page_config 之后）。"""
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)
