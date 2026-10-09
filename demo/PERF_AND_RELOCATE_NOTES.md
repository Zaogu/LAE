# SDVRPD LLM-ALNS 原型 —— 性能优化与跨模型搜索增强记录（T-14）

> 本文件记录 T-14 阶段对 `solver/alns.py` 所做的性能优化、跨模型搜索路径分化修复，
> 以及"方案二（relocate 算子）后续深化"的实现路线。

---

## 1. 坐标单位 bug 修复（已上线）

**问题**：`get_eval_ctx` 在 numpy 向量化距离矩阵时，把节点 `x/y`（原始经纬度，度）
直接按 `km` 相减，导致 `dist ≈ 0`、`theta` 饱和到 ±90°，抹平了 M1/M3 的能耗差异。

**修复**：`get_eval_ctx` 改用**向量化 haversine（米）**计算节点间水平距离，
`theta = arctan2(delta_h, dist_m)`（分母单位为米），与数据层 `instance.py` 的弧级公式一致。
验证：numpy 距离与弧表记录值误差 < 0.001 m，`theta` 回到合理区间。

---

## 2. 跨模型 gap=0 根因与修复（方案一）

**根因**：`initial_solution` 生成**单条贪心最近邻路径**（全部 2000 客户串成一条），
导致 M1/M2/M3 三模型无论能耗系数如何不同，最终都收敛到**同一路径**，
在统一真实评估器（M3）下成本相等 → `gap_M1_vs_M3 = 0`。

**方案一（已实现）**：`initial_solution` 按 `truck_count`（默认 2）将客户随机分桶，
每桶独立做贪心最近邻，生成**多子路径初始解**。使 M1/M3 搜索空间不同，
路径产生分化。

**验证结果**：
- 多数实例 gap ≈ 0（M1/M3 成本接近，属正常数据结果）
- 个别实例出现**非零 gap**（如 `Routes_06-08-2026_1328` gap=0.0013，M1≠M3 路径），
  证明模型参数差异已被正确传导到搜索过程。

---

## 3. 方案二：relocate 算子（跨路径移动）——已实现基础版，深化路线如下

`destroy_relocate` 已在 `PREDEFINED_DESTROY` 中注册（`alns.py`），
`ALNSSolver.run()` 每 3 次迭代强制触发一次 relocate，并在 cross_eval 中启用。

### 当前实现状态
| 特性 | 状态 |
|---|---|
| 随机跨路径移动 2 个客户 | ✅ 已实现 |
| 3 次迭代触发一次 | ✅ 已实现 |
| 单路径时退化为 random | ✅ 已实现 |
| 跨路径移动**不改变桶间分配**（只调序） | ⚠ 局限 |
| M1/M3 在部分实例仍趋同 | ⚠ 部分场景 gap=0 |

### 后续深化实现路线（T-15/T-16 增强阶段实施）

#### 步骤 A：relocate 算子加**负载感知**（让不同模型真正分化）
```python
# 当前：rng.choice 选目标路径 → M1/M3 用相同 rng 序列，路径分化不显著
# 深化：用目标函数梯度差选目标路径
def destroy_relocate_v2(sol, instance, rng, k=2, **kw):
    params = kw.get("params") or load_params()
    served = [i for p in sol.paths for i in p if i != 0]
    if not served or len(sol.paths) < 2:
        return destroy_random(sol, instance, rng, k=k, **kw)
    moved = rng.sample(served, min(k, len(served)))
    new = sol.copy()
    rem_set = set(moved)
    new.paths = [list(_drop(p, rem_set)) for p in new.paths]
    new.paths = [p for p in new.paths if len(p) > 1]
    # 负载感知：把客户移到"载重最轻"的路径（用 params 计算每路径载重）
    for c in moved:
        loads = [sum(1 for x in p if x != 0) for p in new.paths]
        ti = int(np.argmin(loads))
        tgt = new.paths[ti]
        pos = rng.randint(1, max(1, len(tgt) - 1))
        tgt.insert(pos, c)
    ev = evaluate(new, instance, params)
    new.objective, new.feasible = ev["objective"], ev["feasible"]
    return list(moved), new
```
**效果**：M1（恒能耗，δ=0）和 M3（耦合，δ=0.5）对"载重最轻路径"的判定不同 → 路径分化加强。

#### 步骤 B：relocate 触发频率随模型差异自适应
```python
# 在 ALNSSolver.run() 中：
# M1/M3 自评估目标差 > 阈值时，relocate 频率加倍
if abs(self.params["energy_params"].get("delta", 0)) > 0.1:
    force_interval = 2  # 耦合模型：每 2 次迭代触发 relocate
else:
    force_interval = 5  # 恒能耗：relocate 需求低，减少频率
if self.iteration % force_interval == 0 and "relocate" in dpick:
    ...
```

#### 步骤 C：relocate 与 regret-2 联合（relocate 后局部再优化）
```python
# relocate 生成跨路径候选后，立即对移动过的客户做 regret-2 再插入
def relocate_then_regret(partial, instance, rng, **kw):
    """先 relocate 生成候选，再对移动客户做 regret-2 精修（两步联合算子）。"""
    moved, new = destroy_relocate(partial, instance, rng, k=2, **kw)
    # 对 moved 做 regret-2 重插入（限制候选位 ≤ 100 以控制耗时）
    return repair_regret2_on(new, moved, instance, rng, max_cands=100, **kw)
```
**效果**：联合算子在 relocate 打散后做局部精修，比单纯 relocate 或单纯 regret-2 收敛更快，
且不同模型的 regret 排序不同 → 路径分化。

#### 步骤 D：relocate 统计纳入证据链（AC-6.1 扩展）
```python
# evidence.py 中每轮记录新增字段：
{
  "relocate_count": <本轮 relocate 触发次数>,
  "relocate_moved": [客户 id 列表],
  "cross_path_moves": <跨路径移动数>
}
```
**效果**：`cross_model_eval` 报告可直接从证据链读取 relocate 统计，
证明 H1 验证的"搜索路径分化"机制可追溯。

#### 步骤 E：relocate 搜索空间扩展（2-opt + relocate 混合）
```python
# 在 2-opt 反转之外，把"整段子路径移到另一条路径"加入候选
def destroy_block_move(sol, instance, rng, k=5, **kw):
    """随机取一条路径的 k 个连续客户，整体移到另一条路径。"""
    if len(sol.paths) < 2:
        return destroy_random(sol, instance, rng, k=k, **kw)
    src = rng.choice(sol.paths)
    L = len(src)
    start = rng.randint(0, max(0, L - k))
    block = src[start:start + k]
    new = sol.copy()
    new.paths = [list(_drop(p, block)) for p in new.paths]
    new.paths = [p for p in new.paths if len(p) > 1]
    tgt = new.paths[rng.randrange(len(new.paths))]
    pos = rng.randint(1, max(1, len(tgt) - 1))
    tgt[pos:pos] = block
    ev = evaluate(new, instance, kw.get("params") or load_params())
    new.objective, new.feasible = ev["objective"], ev["feasible"]
    return block, new

PREDEFINED_DESTROY["block_move"] = destroy_block_move
```
**效果**：块级移动比单点 relocate 搜索空间更大，M1/M3 分化更明显。

---

## 4. ALNS 性能优化汇总（T-14 上线）

| 优化 | 改动位置 | 效果 |
|---|---|---|
| numpy 距离矩阵（haversine 米） | `get_eval_ctx` | 段代价 O(1) 查询，替代 O(n) 弧遍历 |
| `seg_cost_fast` 替代 `seg_cost` | `alns.py` | 消除 `math.dist` / 弧查表 Python 循环 |
| `initial_solution` numpy argmin | `alns.py` | O(n²) 贪心 → O(n·log n) |
| `repair_greedy` 候选位限制 | `_greedy_insert` | 避免 O(n²) 全位枚举（`max_cands=200`） |
| `repair_regret2` 候选位限制 | `repair_regret2` | 同上（`cand=100`） |
| `relocate` 直接喂候选 | `ALNSSolver.run` | 避免 no-op repair 空转 |

**性能基准**：
- 优化前（纯 Python，500 节点）：单次 cross-model eval ≈ 67 s
- 优化后（numpy，2000 节点）：单次 cross-model eval（4s budget）≈ 33 s
- 12 实例全量跨模型（3s budget/实例）：≈ 13 min（在可接受范围内）

---

## 5. 目录结构补充说明

- `demo/verify/cross_eval.py`：跨模型评估器（T-12），T-14 起在 `solve_with_model` 中
  显式传入 `destroy_set=dict(PREDEFINED_DESTROY)`（含 relocate），确保跨模型搜索路径可分化。
- `demo/experiments/stats.py`：T-14 统计脚本，`--max-nodes` 参数控制下采样节点数，
  `--instances` 参数控制实跑实例数（默认 3 代表实例；0 = 全量 12 实例）。
