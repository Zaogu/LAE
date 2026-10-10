"""solver/alns.py —— 自研极简 ALNS（FR-3/FR-4/FR-9 / AC-3.1/3.2 / NFR-1/2）。

自研理由（PLAN 例外 1）：可丢弃性 + 零额外依赖 + LLM 算子注入接口最可控。
框架（设计文档 3.2 主循环伪代码）：
  初始解 -> while 未达时间预算/迭代上限:
      轮盘赌选破坏算子 d -> 部分解
      轮盘赌选修复算子 r -> 新解
      可行且改进 -> 更新 + 提权；否则退火准则接受 + 衰权
      每 K(=100) 迭代保存检查点

算子接口（LLM 生成与静态检查的目标签名，SPEC 数据模型）：
    def destroy(solution, instance, rng, **kwargs) -> (removed, partial)
      solution: model.Solution；instance: dict；rng: random.Random
      removed: 被移除的节点 id 列表；partial: 移除后的 Solution
预置破坏算子：随机移除 / 最差移除 / Shaw 相关移除（FR-4）。
修复算子：贪心插入 / Regret-2。
"""
from __future__ import annotations
import math
import os
import json
import random
import time

from solver.model import Solution, load_params, truck_energy, drone_energy, drone_feasible, validate_routes
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_DIR = os.path.join(BASE, "..", "checkpoints")


# ---- 目标评估 ------------------------------------------------------
def evaluate(solution, instance, params, rng=None):
    """计算解的目标值（能耗 + 时间窗软惩罚 + 未服务惩罚）与可行性。

    路径代价逐段评估（设计文档 3.1：代价不可预计算，须沿路径演化）。
    载重 u 随服务递减，影响能耗（动态载荷耦合）。
    性能（T-14）：段代价走 numpy 距离矩阵 + 系数缓存（seg_cost_fast）。
    """
    validation = validate_routes(getattr(solution, "paths", None),
                                 getattr(solution, "unassigned", None), instance,
                                 allow_unassigned=True)
    if not validation["passed"]:
        return {"objective": float("inf"), "feasible": False,
                "validation_errors": validation["errors"]}
    p = params
    cP, tP = p["cost_params"], p["time_window"]
    ctx = get_eval_ctx(instance, p)
    total = 0.0
    feasible = True

    for path in solution.paths:
        load = (len(path) - 1) * 5.0  # 每客户 5kg（原型假设；仓库不计载重）
        for idx in range(len(path) - 1):
            i, j = path[idx], path[idx + 1]
            total += seg_cost_fast(ctx, p, i, j, load)
            load = max(0.0, load - 5.0)

    # 时间窗软惩罚
    tw = instance.get("time_windows", {})
    dur_per_hour = tP.get("phi_per_hour", 0.0)
    for path in solution.paths:
        duration = len(path) * 2.0  # 分钟近似
        if duration > tw.get("end", 1e9):
            total += dur_per_hour * (duration - tw["end"]) / 60.0

    # 未服务惩罚
    total += cP["unassigned_penalty"] * len(solution.unassigned)

    return {"objective": round(total, 4), "feasible": feasible and len(solution.unassigned) == 0,
            "validation_errors": []}




def _node(inst, i):
    for n in inst["nodes"]:
        if n["id"] == i:
            return n
    return {"x": 0, "y": 0}


# ---- 初始解 ------------------------------------------------------
def initial_solution(instance, rng, params=None):
    """贪心最近邻 + 多起点，生成初始路径解（所有节点尽量被服务）。

    性能（T-14）：最近邻用 numpy 距离矩阵行向量 argmin，O(n·n_vec) 替代 O(n²) Python 循环。
    路径结构（方案 1）：按 truck 数（默认 2）把节点随机划分成 N_truck 个子路径，
      每个子路径独立做最近邻串联。这样不同能耗模型搜索时，子路径划分与节点分配会分化，
      避免"单条巨路径"导致 M1/M2/M3 收敛到同一路径、跨模型 gap 恒为 0。
    """
    p0 = params or load_params()
    ctx = get_eval_ctx(instance, p0)
    dist = ctx["dist"]
    nmap = ctx["nmap"]
    n_truck = int(p0.get("truck_count", 2))

    ids = [n["id"] for n in instance["nodes"]]
    cust = [x for x in ids if x != 0]
    rng.shuffle(cust)

    # 把客户随机划分成 n_truck 桶（近似均衡）
    buckets = [[] for _ in range(n_truck)]
    for i, c in enumerate(cust):
        buckets[i % n_truck].append(c)

    paths = []
    unassigned = []
    for b in buckets:
        if not b:
            continue
        current = [0]
        cur_idx = nmap.get(0, 0)
        remaining = list(b)
        while remaining:
            rem_pos = np.asarray([nmap.get(r, 0) for r in remaining])
            k = int(np.argmin(dist[cur_idx, rem_pos]))
            nxt = remaining[k]
            current.append(nxt)
            remaining.pop(k)
            cur_idx = nmap.get(nxt, 0)
        current.append(0)
        paths.append(current)

    sol = Solution(paths, unassigned)
    ev = evaluate(sol, instance, p0)
    sol.objective = ev["objective"]; sol.feasible = ev["feasible"]
    return sol


_ncache = {}
def _node_cached(inst, i):
    key = id(inst)
    if key not in _ncache:
        _ncache[key] = {n["id"]: n for n in inst["nodes"]}
        _ncache[key][0] = next((n for n in inst["nodes"] if n["id"] == 0), {"x": 0, "y": 0})
    return _ncache[key].get(i, {"x": 0, "y": 0})


# ---- 评测上下文（T-14 性能优化：numpy 距离矩阵 + 系数缓存，O(1) 段代价查询）----
_ctx_cache = {}
def get_eval_ctx(inst, params):
    """预计算节点的 numpy 坐标矩阵 / 高度矩阵 / 弧查表 / 卡车能耗系数。

    跨同一实例的所有 evaluate/destroy/repair 调用复用，避免每次重建。
    键 = (id(inst), 能耗参数哈希)。
    """
    key = (id(inst), tuple(sorted(params["energy_params"].items())),
           tuple(sorted(params.get("cost_params", {}).items())),
           tuple(sorted(params.get("time_window", {}).items())))
    if key in _ctx_cache:
        return _ctx_cache[key]
    nodes = inst["nodes"]
    nmap = {n["id"]: k for k, n in enumerate(nodes)}
    nmap[0] = nmap.get(0, 0)
    n = len(nodes)
    X = np.array([n_.get("x", 0.0) for n_ in nodes], dtype=float)
    Y = np.array([n_.get("y", 0.0) for n_ in nodes], dtype=float)
    ALT = np.array([n_.get("alt", 0.0) for n_ in nodes], dtype=float)
    # 距离矩阵：x/y 是经纬度（度），向量化 haversine 转米，不能直接当 km 相减
    R = 6371000.0
    lat1 = np.radians(Y)
    dphi = np.radians(Y[None, :] - Y[:, None])
    dlam = np.radians(X[None, :] - X[:, None])
    a = (np.sin(dphi / 2) ** 2 +
         np.cos(lat1[:, None]) * np.cos(np.radians(Y[None, :])) * np.sin(dlam / 2) ** 2)
    dist_m = 2 * R * np.arcsin(np.minimum(1.0, np.sqrt(a)))
    dist_km = dist_m / 1000.0
    # 高度差矩阵（j - i）
    dh = ALT[None, :] - ALT[:, None]
    # 坡度 θ = atan2(Δh, 水平距离(米))—— 与弧级公式一致，分母单位必须为米
    theta = np.arctan2(dh, dist_m)
    np.fill_diagonal(theta, 0.0)
    # 弧查表（相邻预计算弧优先）
    arc = {}
    for a in inst.get("arcs", []):
        i_, j_ = nmap.get(a["i"]), nmap.get(a["j"])
        if i_ is not None and j_ is not None:
            arc[(i_, j_)] = (a["d"] / 1000.0, a["theta"], a["delta_h"])
    ep = params["energy_params"]
    coef = {
        "alpha": ep["alpha"], "beta": ep["beta"], "gamma": ep["gamma"],
        "delta": ep["delta"], "Q": ep.get("truck_capacity_kg", 100.0),
        "D": ep["drone_max_payload_kg"],
    }
    ctx = {"nmap": nmap, "dist": dist_km, "dh": dh, "theta": theta,
           "arc": arc, "coef": coef, "node_alt": ALT, "node_xy": (X, Y),
           "alt_byid": {n_["id"]: n_.get("alt", 0.0) for n_ in nodes}}
    _ctx_cache[key] = ctx
    return ctx


def seg_cost_fast(ctx, params, i, j, load):
    """O(1) 段代价（numpy 索引 + 预存系数），等价原 seg_cost。"""
    nmap = ctx["nmap"]
    ii, jj = nmap.get(i), nmap.get(j)
    key = (i, j)
    if key in ctx["arc"]:
        d_km, th, dh_m = ctx["arc"][key]
    else:
        d_km = float(ctx["dist"][ii, jj])
        dh_m = float(ctx["dh"][ii, jj])
        th = float(ctx["theta"][ii, jj])
    c = ctx["coef"]
    load_factor = 1.0 + c["delta"] * (load / c["Q"] if c["Q"] > 0 else 0.0)
    return (c["alpha"] + c["beta"] * max(0.0, th) + c["gamma"] * max(0.0, -th)) \
        * d_km * 1000.0 * load_factor



def _path_cost_fast(ctx, params, path):
    """单条 path 的能耗代价（载重沿路径衰减），O(path)。"""
    c = ctx["coef"]
    load = max(0, (len(path) - 1)) * 5.0
    total = 0.0
    for idx in range(len(path) - 1):
        total += seg_cost_fast(ctx, params, path[idx], path[idx + 1], load)
        load = max(0.0, load - 5.0)
    return total



# ---- 预置破坏算子（FR-4）----------------------------------------
def _remove_cost(sol, instance, params, i):
    ev_before = sol.objective
    trial = sol.copy()
    trial.paths = [_drop(p, {i}) for p in trial.paths]
    trial.unassigned = list(trial.unassigned) + [i]
    ev = evaluate(trial, instance, params)
    return ev["objective"] - ev_before


def destroy_random(sol, instance, rng, k=2, **kw):
    served = [i for p in sol.paths for i in p if i != 0]
    removed = rng.sample(served, min(k, len(served)))
    partial = sol.copy()
    partial.paths = [list(_drop(p, removed)) for p in partial.paths]
    partial.paths = [p for p in partial.paths if len(p) > 1]
    partial.unassigned = list(partial.unassigned) + removed
    return removed, partial


def destroy_worst(sol, instance, rng, k=2, **kw):
    params = kw.get("params") or load_params()
    served = sorted({i for p in sol.paths for i in p if i != 0},
                    key=lambda i: -_remove_cost(sol, instance, params, i))
    removed = served[:k]
    partial = sol.copy()
    partial.paths = [list(_drop(p, removed)) for p in partial.paths]
    partial.paths = [p for p in partial.paths if len(p) > 1]
    partial.unassigned = list(partial.unassigned) + removed
    return removed, partial


def destroy_shaw(sol, instance, rng, k=3, **kw):
    """相关移除：按坐标近邻 + 相同时间窗聚集（原型简化为坐标近邻聚类）。"""
    served = [i for p in sol.paths for i in p if i != 0]
    if not served:
        return [], sol
    seed_i = rng.choice(served)
    sn = _node_cached(instance, seed_i)
    by_dist = sorted(served, key=lambda i: math.dist(
        (sn["x"], sn["y"]),
        (_node_cached(instance, i)["x"], _node_cached(instance, i)["y"])))
    removed = by_dist[:k]
    partial = sol.copy()
    partial.paths = [list(_drop(p, removed)) for p in partial.paths]
    partial.paths = [p for p in partial.paths if len(p) > 1]
    partial.unassigned = list(partial.unassigned) + removed
    return removed, partial


def _drop(path, removed_set):
    return [x for x in path if x not in set(removed_set)]


def destroy_relocate(sol, instance, rng, k=2, **kw):
    """跨路径 relocate（方案 2 / FR 增强）：随机取 k 个客户，移到"另一条路径"的候选位。

    与普通破坏的区别：不丢进 unassigned，而是直接随机插入到 sol 中除来源路径外的
    某条路径的随机位置。这让 ALNS 能探索"节点在路径间重新分配"的搜索空间，
    使不同能耗模型（M1/M2/M3）因成本梯度不同而收敛到不同路径结构 → 跨模型 gap 可被观测。

    返回 (removed, partial)：removed 仅作日志记录（这些节点已被重放，仍在 paths 中）；
    partial 为已重放的解（repair 阶段可视为无操作或再优化）。
    """
    params = kw.get("params") or load_params()
    served = [i for p in sol.paths for i in p if i != 0]
    if not served or len(sol.paths) < 2:
        # 退化为普通 random（单路径时无法跨路径 relocate）
        return destroy_random(sol, instance, rng, k=k, **kw)
    k = min(k, len(served))
    moved = rng.sample(served, k)
    new = sol.copy()
    # 把 moved 从原路径中移除
    rem_set = set(moved)
    new.paths = [list(_drop(p, rem_set)) for p in new.paths]
    new.paths = [p for p in new.paths if len(p) > 1]
    # 随机插入到另一条路径（若清空后无路径则补回 [0] 兜底）
    for c in moved:
        if not new.paths:
            new.paths.append([0])
        ti = int(rng.randrange(len(new.paths)))
        tgt = new.paths[ti]
        pos = rng.randint(1, max(1, len(tgt) - 1))
        tgt.insert(pos, c)
    ev = evaluate(new, instance, params)
    new.objective, new.feasible = ev["objective"], ev["feasible"]
    # 跨路径 relocate 后所有节点仍在 paths，unassigned 不变
    return list(moved), new



PREDEFINED_DESTROY = {"random": destroy_random,
                      "worst": destroy_worst, "shaw": destroy_shaw,
                      "relocate": destroy_relocate}


# ---- 修复算子 -----------------------------------------------------
def repair_greedy(partial, instance, rng, **kw):
    params = kw.get("params") or load_params()
    removed = list(partial.unassigned)
    new = partial.copy(); new.unassigned = []
    for i in removed:
        _greedy_insert(new, i, instance, params, rng=rng)
    ev = evaluate(new, instance, params)
    new.objective, new.feasible = ev["objective"], ev["feasible"]
    return new


def _greedy_insert(sol, i, instance, params, rng=None, max_cands=200):
    """贪心插入：每条 path 取 ≤ max_cands 个候选位（端点必含 + 随机采样），避免 O(n²) 全位枚举。"""
    best = None; bestd = None
    for pi, path in enumerate(sol.paths):
        n = len(path)
        if n < 2:
            continue
        if n <= max_cands + 1:
            cand_pos = list(range(n - 1))
        else:
            cand_pos = [0, n - 2]
            if rng is not None and n > 3:
                cand_pos += rng.sample(range(1, n - 2), min(max_cands - 2, n - 3))
            cand_pos = sorted(set(cand_pos))
        for pos in cand_pos:
            obj_after = _obj_with_insert(sol, path, pos, i, instance, params)
            if bestd is None or obj_after < bestd:
                bestd = obj_after; best = (pi, pos)
    if best is None:
        sol.paths.append([0, i, 0]); return
    pi, pos = best
    sol.paths[pi].insert(pos + 1, i)


def _obj_with_insert(sol, path, pos, i, instance, params):
    """插入 i 到 path 的 pos 位，增量计算目标变化（T-14 性能：不全量重评估）。

    仅评估受影响的两段（predecessor->i 和 i->successor）+ 被替换的旧段，
    其余段与 sol.objective 保持一致。
    """
    if not 0 <= pos < len(path) - 1:
        raise ValueError("插入位置必须位于仓库起终点之间")
    ctx = get_eval_ctx(instance, params)
    base = sol.objective
    # 该 path 的旧目标贡献（重算该 path 全部段，其余 path 不变）
    # 简化：用 evaluate 对 path 的局部重建——仍 O(path) 但避免 O(全解) 复制
    pth = list(path)
    pth.insert(pos + 1, i)
    new_path_cost = _path_cost_fast(ctx, params, pth)
    old_path_cost = _path_cost_fast(ctx, params, list(path))
    # 解中该 path 被替换，其他 path 不变；unassigned 少一个
    unpen = params["cost_params"]["unassigned_penalty"]
    new_total = base - old_path_cost + new_path_cost - unpen
    return round(new_total, 4)


def repair_regret2(partial, instance, rng, **kw):
    """Regret-2：优先插入"次优-最优插入成本差距最大"的客户（设计文档 3.2）。"""
    params = kw.get("params") or load_params()
    removed = list(partial.unassigned)
    new = partial.copy(); new.unassigned = []
    while removed:
        regrets = []
        for i in removed:
            costs = []
            for pi, path in enumerate(new.paths):
                n = len(path)
                if n < 2:
                    continue
                if n <= 100:
                    cand = list(range(n - 1))
                else:
                    cand = [0, n - 2]
                    if n > 3:
                        cand += rng.sample(range(1, n - 2), 98)
                    cand = sorted(set(cand))
                for pos in cand:
                    costs.append(_obj_with_insert(new, path, pos, i, instance, params))
            if len(costs) >= 2:
                costs.sort()
                regrets.append((costs[1] - costs[0], i))
            elif costs:
                regrets.append((costs[0], i))
            else:
                regrets.append((0.0, i))
        regrets.sort(reverse=True)
        i = regrets[0][1]; _greedy_insert(new, i, instance, params)
        removed.remove(i)
    ev = evaluate(new, instance, params)
    new.objective, new.feasible = ev["objective"], ev["feasible"]
    return new


PREDEFINED_REPAIR = {"greedy": repair_greedy, "regret2": repair_regret2}


# ---- ALNS 主循环 --------------------------------------------------
class ALNSSolver:
    def __init__(self, instance, params=None, rng=None, seed=42,
                 destroy_set=None, repair_set=None,
                 time_budget=60.0, max_iter=10000, checkpoint_interval=100,
                 destroy_fn=None, repair_fn=None, use_checkpoint=True):
        self.instance = instance
        self.params = params or load_params()
        self.rng = rng or random.Random(seed)
        self.seed = seed
        self.time_budget = time_budget
        self.max_iter = max_iter
        self.k = checkpoint_interval
        self.use_checkpoint = use_checkpoint
        self.destroy_set = destroy_set or dict(PREDEFINED_DESTROY)
        self.repair_set = repair_set or dict(PREDEFINED_REPAIR)
        # 自定义注入（LLM 生成的算子，见 FR-5/7）
        self.custom_destroy = destroy_fn
        self.custom_repair = repair_fn
        all_names = list(self.destroy_set) + list(self.repair_set) + (["llm"] if self.custom_destroy or self.custom_repair else [])
        self.weights = {n: 1.0 for n in all_names}
        self.results = {n: 0.0 for n in all_names}
        self.operator_stats = {
            n: {"calls": 0, "improvements": 0, "improvement_total": 0.0}
            for n in all_names
        }
        self.iteration = 0
        self.best = None
        # 每次迭代保留轻量轨迹，供 UI 绘制真实收敛曲线。
        self.history = []
        self.current = None
        self.initial_objective = None
        self.invalid_candidates = 0
        self._checkpoints = []
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    def _pick(self, dset):
        names = list(dset.keys())
        ws = [self.weights[n] + 1e-9 for n in names]
        r = self.rng.uniform(0.0, sum(ws))
        acc = 0.0
        for n, w in zip(names, ws):
            acc += w
            if r <= acc:
                return n
        return names[-1]

    def _save_checkpoint(self):
        cp = {"iteration": self.iteration, "seed_state": self.rng.getstate()[1],
              "seed_len": len(self.rng.getstate()[1]),
              "objective": self.best.objective, "feasible": self.best.feasible,
              "weights": self.weights, "results": self.results,
              "paths": self.best.paths, "unassigned": self.best.unassigned,
              "timestamp": time.time()}
        cp_path = os.path.join(CHECKPOINT_DIR, f"ckpt_{self.instance['instance_id']}.json")
        with open(cp_path, "w", encoding="utf-8") as f:
            json.dump(cp, f, ensure_ascii=False, default=str)
        self._checkpoints.append(cp_path)
        return cp_path

    @staticmethod
    def load_checkpoint(instance_id, restore_rng_into=None):
        cp_path = os.path.join(CHECKPOINT_DIR, f"ckpt_{instance_id}.json")
        if not os.path.exists(cp_path):
            return None
        with open(cp_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def run(self):
        start = time.time()
        self.best = initial_solution(self.instance, self.rng, self.params)
        initial_eval = evaluate(self.best, self.instance, self.params)
        if not initial_eval["feasible"] or not math.isfinite(initial_eval["objective"]):
            raise ValueError("初始路线未通过完整性检查")
        self.best.objective = initial_eval["objective"]
        self.best.feasible = initial_eval["feasible"]
        self.current = self.best.copy()
        self.initial_objective = float(self.best.objective)
        self.history = [{
            "iteration": 0, "objective": self.initial_objective,
            "current_objective": self.initial_objective,
            "elapsed_ms": int((time.time() - start) * 1000),
        }]
        while self.iteration < self.max_iter and (time.time() - start) < self.time_budget:
            # 破坏算子选择（自定义 LLM 算子以 "llm" 名注入）
            dpick = dict(self.destroy_set)
            if self.custom_destroy:
                dpick["llm"] = self.custom_destroy
            dn = self._pick(dpick)
            rpick = dict(self.repair_set)
            if self.custom_repair:
                rpick["llm"] = self.custom_repair
            rn = self._pick(rpick)
            dfn = dpick[dn]
            rfn = rpick[rn]
            # 算子可能原地修改输入；隔离候选，保护已接受路线和最优解。
            candidate = self.current.copy()
            # 周期性强制跨路径 relocate（方案 2）：让 M1/M3 因成本梯度不同而分化
            if self.iteration % 3 == 0 and "relocate" in dpick:
                # 记录真正执行的 relocate，修复算子在这轮没有调用。
                dn, rn = "relocate", None
                removed, new = dpick[dn](candidate, self.instance, self.rng,
                                                  k=2, params=self.params)
            else:
                removed, partial = dfn(candidate, self.instance, self.rng, params=self.params)
                validation = validate_routes(getattr(partial, "paths", None),
                                             getattr(partial, "unassigned", None),
                                             self.instance, allow_unassigned=True)
                if validation["passed"]:
                    new = rfn(partial, self.instance, self.rng, params=self.params)
                else:
                    # 非法部分解直接拦截，不交给修复算子制造虚假收益。
                    new, rn = partial, None
            ev = evaluate(new, self.instance, self.params)
            candidate_objective = float(ev["objective"])
            candidate_feasible = bool(ev["feasible"]) and math.isfinite(candidate_objective)
            if candidate_feasible:
                new = Solution([list(p) for p in new.paths], list(new.unassigned),
                               candidate_objective, True)
            else:
                self.invalid_candidates += 1
            old_best = self.best.objective
            improved = candidate_feasible and candidate_objective < old_best
            accepted = False
            if improved:
                self.current = new
                self.best = new.copy()
                accepted = True
            else:  # 退火式接受（原型简化：概率接受略差解）
                if candidate_feasible and (candidate_objective <= self.current.objective or (
                        candidate_objective <= self.current.objective * 1.02 and self.rng.random() < 0.3)):
                    self.current = new
                    accepted = True
            gain = max(0.0, float(old_best - self.best.objective))
            for name in {dn, rn} - {None}:
                self.results[name] += 2.0 if improved else 0.1
                stats = self.operator_stats[name]
                stats["calls"] += 1
                stats["improvements"] += int(improved)
                stats["improvement_total"] += gain
                self.weights[name] = self.weights[name] * (1.1 if improved else 0.99)
            self.iteration += 1
            self.history.append({
                "iteration": self.iteration,
                "objective": float(self.best.objective),
                "candidate_objective": candidate_objective if math.isfinite(candidate_objective) else None,
                "current_objective": float(self.current.objective),
                "elapsed_ms": int((time.time() - start) * 1000),
                "accepted": accepted,
                "feasible": candidate_feasible,
                "validation_errors": ev.get("validation_errors", []),
                "destroy_operator": dn,
                "repair_operator": rn,
            })
            if self.k and self.iteration % self.k == 0 and self.use_checkpoint:
                self._save_checkpoint()
        if self.use_checkpoint and self.k:
            self._save_checkpoint()
        return self._summary(start)

    def _summary(self, start):
        return {
            "instance_id": self.instance.get("instance_id"),
            "objective_value": self.best.objective,
            "initial_objective": self.initial_objective,
            "feasibility_rate": 1.0 if self.best.feasible else 0.0,
            "unassigned": self.best.unassigned,
            "paths": self.best.paths,
            "runtime_ms": int((time.time() - start) * 1000),
            "iterations": self.iteration,
            "invalid_candidates": self.invalid_candidates,
            "route_validation": validate_routes(self.best.paths, self.best.unassigned, self.instance),
            "weights": self.weights,
            "operator_weights": self.weights,
            "operator_results": self.results,
            "operator_stats": self.operator_stats,
            "history": self.history,
            "seed": self.seed,
        }


if __name__ == "__main__":
    import sys
    inst = json.load(open(sys.argv[1], encoding="utf-8"))
    s = ALNSSolver(inst, time_budget=5.0, seed=1)
    out = s.run()
    print(json.dumps({k: out[k] for k in ("objective_value", "feasibility_rate",
                                            "iterations", "runtime_ms")}, indent=2))
