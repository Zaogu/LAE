"""ui/config_tab.py —— LLM API 配置 Tab（FR-15 / AC-8.1/8.2）。

职责：
- 在 Streamlit 配置页填写 provider / base_url / model / temperature / max_tokens。
- 保存到 config/llm_config.json（持久化，求解器可读）。
- "测试连接"按钮：有网返回 ok / 无网返回明确失败（AC-8.2）。

设计要点：
- 未填写时求解器自动降级（AC-8.2 / EC-7）。
- 零前端成本：纯 Streamlit 表单。
"""
from __future__ import annotations
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "llm_config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "enabled": False,
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
        "temperature": 0.2,
        "max_tokens": 1500,
        "timeout": 60,
    }


def save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def test_connection(cfg: dict, timeout: int = 10) -> dict:
    """测试 LLM API 连接。返回 {ok: bool, message: str}。

    使用 requests 发送一个最小 chat 请求。无网 / 401 / 超时 -> ok=False。
    """
    try:
        import requests
        base = cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
        resp = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.get('api_key', '')}",
                     "Content-Type": "application/json"},
            json={"model": cfg.get("model", "gpt-4o-mini"),
                  "max_tokens": 1,
                  "messages": [{"role": "user", "content": "ping"}]},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return {"ok": True, "message": f"连接成功 (HTTP 200)"}
        elif resp.status_code in (401, 403):
            return {"ok": False, "message": f"认证失败 (HTTP {resp.status_code})：API key 无效"}
        else:
            return {"ok": False, "message": f"API 返回 HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}


def render_config_tab() -> None:
    """在 Streamlit app 中渲染配置 Tab。"""
    import streamlit as st
    st.caption("填写 OpenAI 兼容 API 信息，保存后求解器将调用 LLM 生成破坏算子。"
               "未配置时系统自动降级到预置算子。")

    cfg = load_config()
    with st.form("llm_config_form"):
        st.write("当前配置：")
        st.json({k: ("***" if k == "api_key" and v else v) for k, v in cfg.items()})

        provider = st.text_input("Provider", value=cfg.get("provider", "openai"))
        base_url = st.text_input("Base URL", value=cfg.get("base_url", "https://api.openai.com/v1"))
        api_key = st.text_input("API Key (secret)", value=cfg.get("api_key", ""),
                                type="password")
        model = st.text_input("Model", value=cfg.get("model", "gpt-4o-mini"))
        temperature = st.slider("Temperature", 0.0, 2.0,
                                 value=float(cfg.get("temperature", 0.2)), step=0.1)
        max_tokens = st.number_input("Max Tokens", min_value=100, max_value=8000,
                                     value=int(cfg.get("max_tokens", 1500)))
        timeout = st.number_input("Timeout (s)", min_value=5, max_value=300,
                                  value=int(cfg.get("timeout", 60)))
        submitted = st.form_submit_button("保存配置")

    if submitted:
        new_cfg = {
            "enabled": True,
            "provider": provider,
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        save_config(new_cfg)
        st.success("配置已保存")

        if st.button("测试连接"):
            result = test_connection(new_cfg)
            if result["ok"]:
                st.success(result["message"])
            else:
                st.error(result["message"])

    # 显示当前状态
    enabled = cfg.get("enabled", False) and bool(cfg.get("api_key"))
    if enabled:
        st.success("LLM 已启用，求解器将调用 LLM 生成破坏算子")
    else:
        st.info("LLM 未启用（无 API key 或 enabled=false），求解器将降级到预置算子")
