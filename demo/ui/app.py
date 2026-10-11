"""ui/app.py —— SDVRPD 路径优化工作台（Streamlit 控制台入口）。

结构：
  侧边栏：产品名 + 导航（求解 / 结果分析 / 模型配置）
  主内容：页头 + 页面主体

设计：浅色工程工作台（雾白背景 / 白色表面 / 石墨文字 / 低饱和蓝主操作）。
本文件只负责布局与导航；求解语义（预算、随机种子、模型调用、结果与导出）
保持在 solve_page / results_page / config_page 中，与原实现一致。
"""
from __future__ import annotations
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from ui.styles import inject, ambient_layer
from ui.components import sidebar_brand, page_head

PAGES = ["求解", "结果分析", "模型配置"]

st.set_page_config(page_title="SDVRPD 路径优化工作台", page_icon="🛩", layout="wide")
inject()
ambient_layer()
sidebar_brand()

nav = st.sidebar.radio("导航", PAGES, label_visibility="collapsed", key="nav_page")

PAGE_META = {
    "求解": ("求解", "选择实例与参数，运行 ALNS 求解并查看本次结果。"),
    "结果分析": ("结果分析", "查看当前运行的路径方案、搜索过程与生成记录，并导出证据。"),
    "模型配置": ("模型配置", "配置大模型服务；未启用时求解器自动使用预置算子。"),
}

title, subtitle = PAGE_META[nav]
page_head(title, subtitle)

if nav == "求解":
    from ui import solve_page
    solve_page.render()
elif nav == "结果分析":
    from ui import results_page
    results_page.render()
else:
    from ui import config_page
    config_page.render()
