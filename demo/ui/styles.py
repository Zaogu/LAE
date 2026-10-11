"""ui/styles.py —— 设计令牌与全局样式（冷白工程工作台 + 缓慢环境光）。

只使用 Streamlit 官方稳定的 data-testid 属性（stApp / stSidebar / stTabs 等），
不依赖易失效的内部 DOM 层级选择器。

配色（冷白底色 + 深靛蓝操作色 + 青蓝环境光）
  页面底色 #F6F8FC · 内容表面 #FFFFFF · 次级表面 #F0F4FA
  主文字 #182235 · 次级文字 #59677B · 辅助文字 #69778A · 边框 #E1E7F0
  主操作 #3659D9 · hover #2948BB · 选中底 #EDF2FF
  成功 #18794E · 提醒 #9A6400 · 错误 #C43D3D
青色只用于环境光与图表分类色。
"""
from __future__ import annotations

# ---- 设计令牌 --------------------------------------------------------------
BG = "#F6F8FC"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F0F4FA"
TEXT = "#182235"
TEXT_MUTED = "#59677B"
TEXT_FAINT = "#69778A"
BORDER = "#E1E7F0"
BORDER_STRONG = "#CBD5E5"
PRIMARY = "#3659D9"
PRIMARY_HOVER = "#2948BB"
SELECTED_BG = "#EDF2FF"
SUCCESS = "#18794E"
WARN = "#9A6400"
DANGER = "#C43D3D"

# 路径分类配色：蓝色系为主 + 暖橙，跨 2D / 3D / 图例 / 摘要一致
PATH_COLORS = [
    "#3659D9",  # 靛蓝（主）
    "#E07A3F",  # 暖橙
    "#2F7FB8",  # 中蓝
    "#C2542A",  # 赭橙
    "#5B8FD6",  # 浅蓝
    "#A8571F",  # 深橙
    "#7BA7E0",  # 更浅蓝
    "#D99A6C",  # 浅橙
]

FONT_STACK = ('-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", '
              '"PingFang SC", "Hiragino Sans GB", Roboto, "Helvetica Neue", Arial, sans-serif')
MONO_STACK = ('"Cascadia Code", "SF Mono", Consolas, "Liberation Mono", Menlo, monospace')

CSS = """
<style>
:root {
  --bg: #F6F8FC;
  --surface: #FFFFFF;
  --surface-alt: #F0F4FA;
  --text: #182235;
  --text-muted: #59677B;
  --text-faint: #69778A;
  --border: #E1E7F0;
  --border-strong: #CBD5E5;
  --primary: #3659D9;
  --primary-hover: #2948BB;
  --selected-bg: #EDF2FF;
  --success: #18794E;
  --warn: #9A6400;
  --danger: #C43D3D;
  --shadow: 0 1px 2px rgba(24,34,53,.04), 0 1px 3px rgba(24,34,53,.03);
  --shadow-md: 0 2px 4px rgba(24,34,53,.05), 0 4px 12px rgba(24,34,53,.05);
  --mono: "Cascadia Code", "SF Mono", Consolas, "Liberation Mono", Menlo, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei",
          "PingFang SC", "Hiragino Sans GB", Roboto, "Helvetica Neue", Arial, sans-serif;
}

html, body { background: var(--bg); }
.stApp { background: transparent; }
.stApp, .stMarkdown, .stMarkdown p, label, .stCaption { color: var(--text); }
body, .stApp { font-family: var(--sans); }

/* ============ 环境光背景层（脱离文档流，不改写任何容器定位） ============ */
.ambient-bg {
  position: fixed; inset: 0; z-index: -1; pointer-events: none; overflow: hidden;
  background: var(--bg);
}
.ambient-bg .glow {
  position: absolute; border-radius: 50%;
  will-change: transform;
  transform: translate3d(0,0,0);
}
/* 右上 · 靛蓝 */
.ambient-bg .g1 {
  width: 820px; height: 820px; top: -320px; right: -260px;
  background: radial-gradient(circle, rgba(54,89,217,.085) 0%, rgba(54,89,217,.035) 42%, rgba(54,89,217,0) 70%);
  animation: drift-a 34s ease-in-out infinite alternate;
}
/* 左下 · 青蓝 */
.ambient-bg .g2 {
  width: 700px; height: 700px; bottom: -300px; left: -220px;
  background: radial-gradient(circle, rgba(60,150,190,.075) 0%, rgba(60,150,190,.03) 45%, rgba(60,150,190,0) 72%);
  animation: drift-b 41s ease-in-out infinite alternate;
}
/* 右缘中部 · 浅青 */
.ambient-bg .g3 {
  width: 560px; height: 560px; top: 34%; right: -200px;
  background: radial-gradient(circle, rgba(76,168,196,.065) 0%, rgba(76,168,196,.025) 48%, rgba(76,168,196,0) 74%);
  animation: drift-c 28s ease-in-out infinite alternate;
}
@keyframes drift-a {
  0%   { transform: translate3d(0,0,0) scale(1); }
  50%  { transform: translate3d(-34px, 26px, 0) scale(1.045); }
  100% { transform: translate3d(-16px, 46px, 0) scale(1.02); }
}
@keyframes drift-b {
  0%   { transform: translate3d(0,0,0) scale(1.02); }
  50%  { transform: translate3d(28px, -30px, 0) scale(1.055); }
  100% { transform: translate3d(48px, -14px, 0) scale(1.03); }
}
@keyframes drift-c {
  0%   { transform: translate3d(0,0,0) scale(1.01); }
  50%  { transform: translate3d(-24px,-22px,0) scale(1.06); }
  100% { transform: translate3d(-40px, 8px, 0) scale(1.025); }
}
/* 减少动态效果：静止渐变背景 */
@media (prefers-reduced-motion: reduce) {
  .ambient-bg .glow { animation: none !important; }
}
/* 小屏降低强度 */
@media (max-width: 900px) {
  .ambient-bg .glow { opacity: .65; animation-duration: 60s; }
}

/* 内容背景透明，让 fixed 背景层（z-index:-1）透出；
   不改写 stAppViewContainer / stSidebar 的 position 与 z-index，
   以保持 Streamlit 自身滚动容器行为不变。 */
[data-testid="stMain"] { background: transparent; }

/* ============ 主内容留白 ============ */
/* 只加内边距，不动高度/溢出，避免影响页面滚动。 */
.block-container { padding-top: 1.9rem; padding-bottom: 4rem; max-width: 100%; }
@media (min-width: 1100px) { .block-container { padding-left: 2.25rem; padding-right: 2.25rem; } }
@media (min-width: 1600px) { .block-container { padding-left: 3rem; padding-right: 3rem; } }

/* 顶部栏：只做透明化，不改高度（改 height:0 会破坏 Streamlit 滚动容器的高度计算）。 */
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { display: none; }
[data-testid="stDecoration"] { display: none; }

/* ============ 侧边栏 ============ */
[data-testid="stSidebar"] {
  background: #FCFDFF;
  border-right: 1px solid var(--border);
  width: 228px !important; min-width: 228px !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: .5rem; }
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapsedControl"] button {
  color: var(--text-muted); border-radius: 6px;
}
[data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button:focus-visible,
[data-testid="stSidebarCollapsedControl"] button:focus-visible {
  outline: 2px solid var(--primary); outline-offset: 1px;
}

/* 品牌区 */
.app-sidebar-brand {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 4px 14px 4px; margin: 0 8px 10px 8px;
  border-bottom: 1px solid var(--border);
}
.app-sidebar-brand .mark { flex: 0 0 auto; display: block; }
.app-sidebar-brand .brand-name {
  font-size: 15.5px; font-weight: 700; letter-spacing: .2px;
  color: var(--text); line-height: 1.2;
}
.app-sidebar-brand .brand-sub {
  font-size: 11.5px; color: var(--text-faint); margin-top: 1px; letter-spacing: .2px;
}

/* 导航（radio 伪装成导航项） */
[data-testid="stSidebar"] .stRadio > label { display: none; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] { gap: 3px; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label {
  display: flex; align-items: center; gap: 10px;
  min-height: 40px; padding: 8px 12px; margin: 0;
  border-radius: 8px; border: 1px solid transparent; cursor: pointer;
  transition: background-color .15s ease, border-color .15s ease;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:hover {
  background: var(--surface-alt);
}
/* 隐藏原生圆点 */
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label > div:first-child {
  display: none;
}
/* 选中态：整行背景 + 浅蓝边 + 深蓝文字 */
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(input:checked) {
  background: var(--selected-bg); border-color: #C9D8FB;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label p {
  font-size: 13.5px; color: var(--text); font-weight: 500; margin: 0; line-height: 1.3;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(input:checked) p {
  color: var(--primary-hover); font-weight: 600;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:focus-within {
  outline: 2px solid var(--primary); outline-offset: 1px;
}

/* ============ 页头 ============ */
.page-head { margin: 0 0 24px 0; }
.page-head h1 {
  font-size: 27px; font-weight: 600; color: var(--text); margin: 0;
  line-height: 1.25; letter-spacing: -.3px;
}
.page-head .sub { font-size: 13.5px; color: var(--text-muted); margin-top: 6px; line-height: 1.55; }

/* ============ 小节标题 ============ */
.section-title {
  font-size: 16px; font-weight: 600; color: var(--text);
  margin: 0 0 12px 0; letter-spacing: -.1px; line-height: 1.4;
}
.section-sub { font-size: 13px; color: var(--text-muted); margin: -7px 0 14px 0; line-height: 1.6; }

/* ============ 面板 ============ */
.panel {
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 18px 20px; box-shadow: var(--shadow);
}
.panel.tight { padding: 14px 16px; }
.panel-head {
  font-size: 13px; font-weight: 600; color: var(--text-muted);
  letter-spacing: .3px; text-transform: uppercase; margin-bottom: 12px;
}

/* ============ 指标条 ============ */
.metric-row {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: 1px; background: var(--border); border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden; box-shadow: var(--shadow);
}
.metric-row .m { background: var(--surface); padding: 13px 16px; }
.metric-row .m .label {
  font-size: 12px; color: var(--text-faint); margin-bottom: 5px; letter-spacing: .2px;
  white-space: nowrap;
}
.metric-row .m .value {
  font-size: 19px; font-weight: 600; color: var(--text);
  font-family: var(--mono); font-variant-numeric: tabular-nums;
  line-height: 1.25; white-space: nowrap;
}
.metric-row .m.lead .value { font-size: 23px; font-weight: 650; }
.metric-row .m .value .unit {
  font-size: 12px; color: var(--text-faint); font-weight: 400;
  margin-left: 3px; font-family: var(--sans);
}
.metric-row .m .value.ok { color: var(--success); }
.metric-row .m .value.warn { color: var(--warn); }
.metric-row .m .value.danger { color: var(--danger); }

/* ============ 状态徽标 ============ */
.status-badge {
  display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px;
  font-weight: 550; padding: 3px 10px; border-radius: 999px; border: 1px solid;
  line-height: 1.6; white-space: nowrap;
}
.status-badge .dot { width: 6px; height: 6px; border-radius: 50%; flex: 0 0 auto; }
.status-badge.ok    { color: var(--success); background: #EDF7F2; border-color: #C4E3D3; }
.status-badge.ok .dot { background: var(--success); }
.status-badge.warn  { color: var(--warn); background: #FBF5E6; border-color: #E8D8AE; }
.status-badge.warn .dot { background: var(--warn); }
.status-badge.danger{ color: var(--danger); background: #FBEFEF; border-color: #EDC9C9; }
.status-badge.danger .dot { background: var(--danger); }
.status-badge.idle  { color: var(--text-muted); background: var(--surface-alt); border-color: var(--border-strong); }
.status-badge.idle .dot { background: var(--text-faint); }
.status-badge.run   { color: var(--primary-hover); background: var(--selected-bg); border-color: #C9D8FB; }
.status-badge.run .dot { background: var(--primary); }

/* ============ 键值列表 ============ */
.kv {
  border: 1px solid var(--border); border-radius: 10px; background: var(--surface);
  overflow: hidden; box-shadow: var(--shadow);
}
.kv .row {
  display: flex; justify-content: space-between; align-items: baseline; gap: 16px;
  padding: 9px 15px; border-bottom: 1px solid var(--border);
}
.kv .row:last-child { border-bottom: none; }
.kv .row .k { font-size: 13px; color: var(--text-muted); flex: 0 0 auto; }
.kv .row .v {
  font-size: 13px; color: var(--text); text-align: right;
  word-break: break-word; min-width: 0; line-height: 1.5;
}
.kv .row .v.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; font-size: 12.5px; }

/* ============ 空状态 ============ */
.empty-state {
  border: 1px dashed var(--border-strong); border-radius: 10px;
  background: var(--surface); padding: 28px 24px; text-align: center;
}
.empty-state .es-title { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
.empty-state .es-desc { font-size: 13px; color: var(--text-muted); line-height: 1.65; }

/* ============ 路径图例 ============ */
.legend-list { display: flex; flex-direction: column; gap: 7px; }
.legend-list .item { display: flex; align-items: center; gap: 9px; font-size: 13px; color: var(--text); }
.legend-list .item .swatch {
  width: 11px; height: 11px; border-radius: 3px; flex: 0 0 auto;
}
.legend-list .item .cnt {
  margin-left: auto; color: var(--text-faint); font-family: var(--mono);
  font-size: 12px; font-variant-numeric: tabular-nums;
}

/* 提示条（紧凑辅助信息） */
.notice {
  display: flex; gap: 9px; align-items: flex-start;
  font-size: 12.5px; color: var(--text-muted); line-height: 1.6;
  padding: 9px 13px; border-radius: 8px;
  background: var(--surface-alt); border: 1px solid var(--border);
}
.notice.warn { background: #FBF5E6; border-color: #E8D8AE; color: #7A5000; }
.notice.danger { background: #FBEFEF; border-color: #EDC9C9; color: #9E3030; }

/* ============ 按钮 ============ */
/* Streamlit 1.35 的标记：data-testid="baseButton-<kind>"，
   kind ∈ primary / secondary / primaryFormSubmit / secondaryFormSubmit。 */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button,
[data-testid="stFormSubmitButton"] button,
button[data-testid^="baseButton-"] {
  border-radius: 7px; border: 1px solid var(--border-strong);
  background: var(--surface); color: var(--text);
  font-weight: 550; font-size: 13.5px; min-height: 38px;
  transition: background-color .15s ease, border-color .15s ease, color .15s ease;
  box-shadow: var(--shadow);
}
[data-testid="stButton"] button:hover,
[data-testid="stDownloadButton"] button:hover,
[data-testid="stFormSubmitButton"] button:hover,
button[data-testid^="baseButton-"]:hover {
  border-color: var(--primary); color: var(--primary-hover); background: #F7F9FF;
}
[data-testid="stButton"] button:focus-visible,
[data-testid="stDownloadButton"] button:focus-visible,
[data-testid="stFormSubmitButton"] button:focus-visible,
button[data-testid^="baseButton-"]:focus-visible {
  outline: 2px solid var(--primary); outline-offset: 1px;
}
[data-testid="stButton"] button:disabled,
[data-testid="stDownloadButton"] button:disabled,
[data-testid="stFormSubmitButton"] button:disabled {
  opacity: .5; cursor: not-allowed; box-shadow: none;
}
/* 主按钮：实心靛蓝 + 白字 */
button[data-testid="baseButton-primary"],
button[data-testid="baseButton-primaryFormSubmit"] {
  background: var(--primary) !important;
  border-color: var(--primary) !important;
  color: #FFFFFF !important;
  box-shadow: 0 1px 2px rgba(54,89,217,.22) !important;
}
button[data-testid="baseButton-primary"]:hover,
button[data-testid="baseButton-primaryFormSubmit"]:hover {
  background: var(--primary-hover) !important;
  border-color: var(--primary-hover) !important;
  color: #FFFFFF !important;
}
button[data-testid="baseButton-primary"] *,
button[data-testid="baseButton-primaryFormSubmit"] * {
  color: #FFFFFF !important;
}
button[data-testid="baseButton-primary"]:disabled,
button[data-testid="baseButton-primaryFormSubmit"]:disabled {
  background: #A9B8E8 !important; border-color: #A9B8E8 !important; opacity: 1 !important;
}

/* ============ 输入控件 ============ */
.stTextInput input, .stNumberInput input, .stTextArea textarea {
  background: var(--surface) !important; color: var(--text) !important;
  border-radius: 7px !important;
}
div[data-baseweb="input"], div[data-baseweb="base-input"] {
  background: var(--surface) !important; border-radius: 7px !important;
  border: 1px solid var(--border-strong) !important;
  transition: border-color .15s ease, box-shadow .15s ease;
}
div[data-baseweb="input"]:focus-within, div[data-baseweb="base-input"]:focus-within {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(54,89,217,.12) !important;
}
div[data-baseweb="select"] > div {
  background: var(--surface) !important; border: 1px solid var(--border-strong) !important;
  border-radius: 7px !important; transition: border-color .15s ease, box-shadow .15s ease;
}
div[data-baseweb="select"] > div:focus-within {
  border-color: var(--primary) !important;
  box-shadow: 0 0 0 3px rgba(54,89,217,.12) !important;
}
.stTextInput label, .stNumberInput label, .stSelectbox label, .stSlider label {
  font-size: 13px !important; color: var(--text-muted) !important; font-weight: 500;
}

/* ============ 标签页 ============ */
[data-testid="stTabs"] button[role="tab"] {
  font-size: 14px; font-weight: 550; color: var(--text-muted);
  padding: 8px 4px; transition: color .15s ease;
}
[data-testid="stTabs"] button[role="tab"]:hover { color: var(--text); }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color: var(--primary-hover); }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background: var(--primary); height: 2px; }
[data-testid="stTabs"] [data-baseweb="tab-border"] { background: var(--border); }
[data-testid="stTabs"] button[role="tab"]:focus-visible {
  outline: 2px solid var(--primary); outline-offset: 2px; border-radius: 4px;
}

/* ============ 其他原生元素 ============ */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border); border-radius: 10px; overflow: hidden;
  box-shadow: var(--shadow);
}
[data-testid="stMetricValue"] { font-family: var(--mono); font-variant-numeric: tabular-nums; }
[data-testid="stExpander"] {
  border: 1px solid var(--border) !important; border-radius: 10px !important;
  background: var(--surface); box-shadow: var(--shadow);
}
[data-testid="stExpander"] summary { font-size: 13.5px; color: var(--text-muted); font-weight: 500; }
[data-testid="stExpander"] summary:hover { color: var(--primary-hover); }
hr { border-color: var(--border); margin: 1.6rem 0; }
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] { background: var(--primary); }
[data-testid="stAlert"] { border-radius: 10px; font-size: 13px; }
[data-testid="stCaptionContainer"], .stCaption, [data-testid="stCaption"] {
  color: var(--text-faint) !important; font-size: 12.5px;
}
</style>
"""


def inject() -> None:
    """注入全局样式（每个页面调用一次，位于 set_page_config 之后）。"""
    import streamlit as st
    st.markdown(CSS, unsafe_allow_html=True)


def ambient_layer() -> None:
    """注入环境光背景层（fixed + pointer-events:none，不拦截输入、不动画 blur）。"""
    import streamlit as st
    st.markdown(
        '<div class="ambient-bg" aria-hidden="true">'
        '<div class="glow g1"></div>'
        '<div class="glow g2"></div>'
        '<div class="glow g3"></div>'
        '</div>',
        unsafe_allow_html=True,
    )
