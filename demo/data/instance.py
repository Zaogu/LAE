"""data/instance.py —— 数据层（FR-1 / D6 / AC-1.1 / EC-1 / EC-2）。

职责：
- 读取本地 12 个 Madrid 轨迹 CSV（docs/运行与验证数据/data/Routes_*）。
- 解析航点（Lon/Lat/Alt），计算相邻航点水平距离与高度差，
  得到路段级坡度 θ = arctan(Δh / Δd)。
- 按空域配置（文件名时间戳分组，见 GROUP_MAP）标注 airspace 与 vertical。
- 推断无人机数 W = 该文件中出现的机型数量（SPEC 待澄清#3）。
- 输出标准化 SDVRPD 实例 JSON 到 data/instances/。

设计要点：
- 一个 CSV 对应"一个轨迹文件 = 一个 SDVRPD 实例"。
  航点序列作为客户节点集合 V'；仓库 0 取序列首点（ORG）。
- 坡度矩阵 θ 由相邻航点计算；对缺失高度字段做降级（EC-2）。
"""
from __future__ import annotations
import json
import math
import os
import glob
import pandas as pd
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE, "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "docs", "运行与验证数据", "data")
OUT_DIR = os.path.join(BASE, "instances")

# 12 个文件 -> (airspace, vertical) 正交设计（SPEC/数据说明 7.2）
GROUP_MAP = {
    "Routes_06-08-2026_1125.csv": ("IT", "HIGH"),
    "Routes_06-08-2026_1151.csv": ("IT", "WITH"),
    "Routes_06-08-2026_1214.csv": ("IT", "LOW"),
    "Routes_06-08-2026_1237.csv": ("IT", "BOTTOM"),
    "Routes_06-08-2026_1303.csv": ("LFR", "HIGH"),
    "Routes_06-08-2026_1328.csv": ("LFR", "WITH"),
    "Routes_06-08-2026_1352.csv": ("LFR", "LOW"),
    "Routes_06-08-2026_1418.csv": ("LFR", "BOTTOM"),
    "Routes_06-08-2026_1446.csv": ("CA", "HIGH"),
    "Routes_06-08-2026_1625.csv": ("CA", "WITH"),
    "Routes_06-08-2026_1757.csv": ("CA", "LOW"),
    "Routes_06-08-2026_1938.csv": ("CA", "BOTTOM"),
}


# 流式采样上限：每个实例最多取前 N 个有效航点（百万行 TSV 全量解析过慢；
# 节点/坡度特征用头部 N 点即可支撑原型求解，可按需调大）
MAX_NODES = 2000  # T-14 增大：让跨模型评估（H1 坡度建模）更有说服力；可配置

def _to_finite(val, default):
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def _detect_sep(path: str) -> str:
    """嗅探分隔符：Madrid 路线文件实为 TSV（tab 分隔）；兼容逗号 CSV。"""
    with open(path, "rb") as fp:
        first = fp.readline(1024)
    head = first.decode("utf-8", "ignore")
    if "\t" in head:
        return "\t"
    return ","


def process_one(csv_path: str, filename: str) -> dict:
    """处理单个路线文件，返回 SDVRPD 实例 dict。文件异常向上抛（由调用方隔离）。"""
    airspace, vertical = GROUP_MAP.get(filename, ("IT", "HIGH"))
    sep = _detect_sep(csv_path)
    # 流式采样：只读前 MAX_NODES 个有效航点（避免百万行 TSV 全量解析）
    lon, lat, alt_series, drones_set = [], [], [], set()
    with open(csv_path, "r", encoding="utf-8", errors="ignore") as fh:
        header = next(fh, None)
        cols = [c.strip() for c in (header.split(sep))]
        li = cols.index("Lon") if "Lon" in cols else None
        la = cols.index("Lat") if "Lat" in cols else None
        al = cols.index("Alt") if "Alt" in cols else None
        di = cols.index("Drone") if "Drone" in cols else None
        for line in fh:
            if len(lon) >= MAX_NODES:
                break
            parts = line.rstrip("\n").split("\t" if sep == "\t" else ",")
            if len(parts) < 2:
                continue
            try:
                x = _to_finite(parts[li], float("nan"))
                y = _to_finite(parts[la], float("nan"))
            except IndexError:
                continue
            if x != x or y != y:
                continue
            a = _to_finite(parts[al], 0.0) if al is not None else 0.0
            lon.append(x); lat.append(y); alt_series.append(a)
            if di is not None:
                try:
                    drones_set.add(str(parts[di]))
                except IndexError:
                    pass
    drones = sorted(drones_set)
    w = max(1, len(drones))

    nodes = []
    for idx in range(len(lon)):
        nodes.append({
            "id": idx,
            "x": float(lon[idx]),
            "y": float(lat[idx]),
            "alt": float(alt_series[idx]),
        })

    # 弧：相邻航点，计算水平距离 d 与高度差 Δh，坡度 θ
    arcs = []
    for i in range(len(nodes) - 1):
        a, b = nodes[i], nodes[i + 1]
        d = _haversine_m(a["x"], a["y"], b["x"], b["y"])
        dh = b["alt"] - a["alt"]
        theta = math.atan2(dh, d) if d > 1e-6 else 0.0
        arcs.append({"i": i, "j": i + 1, "d": round(d, 3),
                    "delta_h": round(dh, 3), "theta": round(theta, 6)})

    # 时间窗：用文件起始时间作为 0 点，软时间窗按行索引递增
    tw_start, tw_end = 0, max(60, len(nodes) * 2)
    demands = [1 for _ in nodes]  # 每航点 1 件需求（原型假设值，可配置）

    instance = {
        "instance_id": filename.replace(".csv", ""),
        "filename": filename,
        "airspace": airspace,
        "vertical": vertical,
        "nodes": nodes,
        "arcs": arcs,
        "slope_matrix": [a["theta"] for a in arcs],  # 供数据层->算法层接口（SPEC 7）
        "demands": demands,
        "time_windows": {"start": tw_start, "end": tw_end},
        "drone_types": drones,
        "num_drones": w,
        "num_nodes": len(nodes),
    }
    return instance


def _resolve_csv(p: str) -> str:
    """兼容目录布局：p 是文件则返回；p 是目录（Routes_xxx.csv/ 内嵌同名 .csv）则返回内层文件。"""
    if os.path.isfile(p):
        return p
    if os.path.isdir(p):
        for name in os.listdir(p):
            if name.endswith(".csv"):
                return os.path.join(p, name)
    return p


def build_all(force: bool = False) -> dict:
    """构建 12 实例，逐个隔离失败（EC-1/AC-1.2）。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(DATA_DIR, "Routes_*")))
    result = {"built": [], "skipped": [], "count": 0}
    for fn in files:
        path = _resolve_csv(os.path.join(DATA_DIR, fn))
        out = os.path.join(OUT_DIR, fn.replace(".csv", ".json"))
        try:
            if os.path.exists(out) and not force:
                result["built"].append(fn)
                result["count"] += 1
                continue
            inst = process_one(path, fn)
            with open(out, "w", encoding="utf-8") as f:
                json.dump(inst, f, ensure_ascii=False, indent=2)
            result["built"].append(fn)
            result["count"] += 1
        except Exception as e:
            result["skipped"].append({"file": fn, "reason": f"{type(e).__name__}: {e}"})
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="强制重建实例 JSON")
    args = ap.parse_args()
    rep = build_all(force=args.force)
    print(f"已构建 {rep['count']} 实例，跳过 {len(rep['skipped'])}。")
    for s in rep["skipped"]:
        print(f"  [跳过] {s['file']}: {s['reason']}")
