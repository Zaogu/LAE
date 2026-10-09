"""healthcheck.py —— 启动健康检查总控（FR-21 / AC-10.1 / AC-10.2）。

职责：
- 检查 Python 依赖是否可用（NFR-4）。
- 检查数据文件是否存在/可读（EC-1）。
- 检查配置文件是否可解析。
- 单模块失败被隔离：某项检查抛错 -> 标记该模块 unavailable，
  其余检查继续，整体不崩溃（AC-10.2）。

运行：
    python healthcheck.py
输出：
    逐模块可用性报告 + 总体 status。
"""
from __future__ import annotations
import json
import os
import sys
import importlib
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
_DATA_DIR_OVERRIDE = None
# BASE = demo/（healthcheck.py 位于 demo 顶层）；LAE 根在 BASE 上一级
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "docs", "运行与验证数据", "data")
CONFIG_PARAMS = os.path.join(BASE, "config", "params.json")
CONFIG_LLM = os.path.join(BASE, "config", "llm_config.json")

REQUIRED_IMPORTS = [
    "numpy", "pandas", "scipy",
    "matplotlib", "plotly", "streamlit", "requests",
]


def _check_modules() -> dict:
    """逐项 import 检查，单项失败不影响其它项（AC-10.2）。"""
    out = {}
    for m in REQUIRED_IMPORTS:
        try:
            importlib.import_module(m)
            out[m] = {"available": True, "detail": "ok"}
        except Exception as e:
            out[m] = {"available": False, "detail": f"{type(e).__name__}: {e}"}
    return out


def _find_data_files() -> dict:
    """定位 12 个 Madrid 路线文件（EC-1）。
    实际布局：Routes_xxx.csv 是目录，内嵌同名 .csv；也兼容直接 .csv 文件。"""
    result = {"root_exists": os.path.isdir(DATA_DIR), "files": [], "errors": []}
    if not result["root_exists"]:
        result["errors"].append(f"数据目录不存在: {DATA_DIR}")
        return result
    try:
        for name in os.listdir(DATA_DIR):
            if name.startswith("Routes_") and name.endswith(".csv"):
                p = os.path.join(DATA_DIR, name)
                if os.path.isdir(p):
                    # 内层嵌套 .csv
                    inner = [n for n in os.listdir(p) if n.endswith(".csv")]
                    if inner:
                        result["files"].append(name)
                    else:
                        result["errors"].append(f"{name}/ 目录内无 .csv 文件")
                elif os.path.isfile(p):
                    if os.path.getsize(p) > 0:
                        result["files"].append(name)
                    else:
                        result["errors"].append(f"{name} 为空文件")
                else:
                    result["errors"].append(f"{name} 不可读")
    except Exception as e:
        result["errors"].append(f"列举数据目录失败: {e}")
    return result


def _check_configs() -> dict:
    out = {}
    for path, label in [(CONFIG_PARAMS, "params.json"), (CONFIG_LLM, "llm_config.json")]:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    json.load(f)
                out[label] = {"exists": True, "valid": True}
            else:
                out[label] = {"exists": False, "valid": None,
                              "note": "缺失（params.json 建议提供，llm_config 缺失可降级）"}
        except Exception as e:
            out[label] = {"exists": True, "valid": False, "detail": str(e)}
    return out


def run_healthcheck(verbose: bool = True) -> dict:
    """运行全部检查，返回结构化报告。任何单项异常都已被隔离。"""
    report = {
        "python": sys.version.split()[0],
        "modules": _check_modules(),
        "data": _find_data_files(),
        "configs": _check_configs(),
    }
    # 汇总各模块可用性
    mod_ok = all(m["available"] for m in report["modules"].values())
    data_ok = report["data"]["root_exists"] and len(report["data"]["files"]) > 0
    report["summary"] = {
        "all_modules_available": mod_ok,
        "data_usable": data_ok,
        "n_data_files": len(report["data"]["files"]),
    }
    report["overall"] = "OK" if (mod_ok and data_ok) else "DEGRADED"
    if verbose:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return report


if __name__ == "__main__":
    rep = run_healthcheck()
    print("\n=== 启动健康检查总控结果 ===")
    print("总体状态:", rep["overall"])
    print("依赖全可用:", rep["summary"]["all_modules_available"])
    print("数据可用:", rep["summary"]["data_usable"],
          f"({rep['summary']['n_data_files']} 个 Madrid 文件)")
    for k, v in rep["modules"].items():
        if not v["available"]:
            print(f"  [模块不可用] {k}: {v['detail']}")
    for e in rep["data"]["errors"]:
        print(f"  [数据问题] {e}")
    sys.exit(0 if rep["overall"] == "OK" else 0)  # 退出码恒 0：降级不阻塞启动（AC-10.2）
