"""ui/config_page.py —— 模型配置页：服务摘要 + 设置表单 + 真实连接测试。

语义与原 ui/config_tab.py 一致：读写 config/llm_config.json，字段不变
（enabled / provider / base_url / api_key / model / temperature / max_tokens / timeout）。
"""
from __future__ import annotations
import json
import os

import streamlit as st

from ui.components import section_title, kv_list, status_badge

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "llm_config.json")

DEFAULTS = {
    "enabled": False,
    "provider": "openai",
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4o-mini",
    "temperature": 0.2,
    "max_tokens": 1500,
    "timeout": 60,
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            merged = dict(DEFAULTS)
            merged.update(cfg if isinstance(cfg, dict) else {})
            return merged
        except Exception:
            pass
    return dict(DEFAULTS)


def save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def test_connection(cfg: dict, timeout: int = 10) -> dict:
    """真实连接测试：向 base_url 发最小 chat 请求。返回 {ok, message}。"""
    try:
        import requests
        base = (cfg.get("base_url") or "").rstrip("/")
        if not base:
            return {"ok": False, "message": "未填写 Base URL"}
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.get('api_key', '')}",
                     "Content-Type": "application/json"},
            json={"model": cfg.get("model", "gpt-4o-mini"), "max_tokens": 1,
                  "messages": [{"role": "user", "content": "ping"}]},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return {"ok": True, "message": "连接成功（HTTP 200）"}
        if resp.status_code in (401, 403):
            return {"ok": False, "message": f"认证失败（HTTP {resp.status_code}）：API Key 无效"}
        return {"ok": False, "message": f"服务返回 HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}


def render():
    cfg = load_config()
    enabled = bool(cfg.get("enabled")) and bool(cfg.get("api_key"))

    # ---- 摘要 ----
    section_title("当前服务")
    left, right = st.columns([2, 1])
    with left:
        kv_list([
            ("启用状态", "已启用" if enabled else "未启用"),
            ("提供商", cfg.get("provider")),
            ("模型", cfg.get("model")),
            ("API 地址", cfg.get("base_url")),
            ("API Key", "已配置" if cfg.get("api_key") else "未配置"),
        ])
    with right:
        if enabled:
            st.markdown(status_badge("ok", "模型服务已启用"), unsafe_allow_html=True)
            st.caption("求解器将调用该服务生成破坏算子。")
        else:
            st.markdown(status_badge("idle", "模型服务未启用"), unsafe_allow_html=True)
            st.caption("求解器将使用预置破坏算子（不调用外部服务）。")

    with st.expander("查看配置详情", expanded=False):
        st.json({k: ("***" if k == "api_key" and v else v) for k, v in cfg.items()})

    st.write("")
    st.divider()
    section_title("设置")

    with st.form("llm_config_form"):
        st.markdown('<div style="font-size:13px;color:#626B78;margin-bottom:6px;">常用</div>',
                    unsafe_allow_html=True)
        provider = st.text_input("提供商", value=cfg.get("provider", "openai"),
                                 help="用于标识服务来源，如 openai / deepseek。")
        base_url = st.text_input("API 地址", value=cfg.get("base_url", ""),
                                 help="OpenAI 兼容的 /v1 根地址。")
        api_key = st.text_input("API Key", value=cfg.get("api_key", ""), type="password",
                                help="以密文保存到 config/llm_config.json，界面不回显明文。")
        model = st.text_input("模型", value=cfg.get("model", ""))

        with st.expander("高级设置", expanded=False):
            temperature = st.slider("Temperature", 0.0, 2.0,
                                    value=float(cfg.get("temperature", 0.2)), step=0.1)
            max_tokens = st.number_input("最大 Token", min_value=100, max_value=8000,
                                         value=int(cfg.get("max_tokens", 1500)))
            timeout = st.number_input("超时（秒）", min_value=5, max_value=300,
                                      value=int(cfg.get("timeout", 60)))

        c1, c2, _ = st.columns([1, 1, 3])
        submitted = c1.form_submit_button("保存配置", type="primary", use_container_width=True)
        test_clicked = c2.form_submit_button("测试连接", use_container_width=True)

    if submitted:
        new_cfg = {
            "enabled": bool(api_key),
            "provider": provider,
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        try:
            save_config(new_cfg)
            st.success("配置已保存。" + ("模型服务已启用。" if new_cfg["enabled"]
                                        else "未填写 API Key，求解器将使用预置算子。"))
        except Exception as e:
            st.error(f"保存失败：{type(e).__name__}: {e}")
            st.caption("输入内容已保留，修正后可再次保存。")

    if test_clicked:
        candidate = {
            "provider": provider, "base_url": base_url, "api_key": api_key,
            "model": model, "temperature": temperature,
            "max_tokens": max_tokens, "timeout": timeout,
        }
        if not candidate["api_key"]:
            st.warning("未填写 API Key，无法测试连接。")
        else:
            with st.spinner("正在测试连接…"):
                res = test_connection(candidate)
            if res["ok"]:
                st.success(res["message"])
            else:
                st.error(res["message"])
