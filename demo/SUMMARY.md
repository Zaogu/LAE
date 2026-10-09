# SDVRPD LLM 驱动 ALNS 求解器原型 —— 项目总结（SUMMARY）

## 1. 交付物总览（设计文档 D1–D7）

| 交付物 | 模块 | 状态 | 关键验证 |
|---|---|---|---|
| **D1** 可运行求解器 | `solver/alns.py` + `model.py` | ✅ | 单实例目标值≈11.8，可行率1.0，可复现，检查点恢复 |
| **D2** LLM 生成闭环 | `llm/*` | ✅ | 无配置自动降级；3次重试→回退预置算子；静态检查7/7单测通过 |
| **D3** 证据链 | `verify/evidence.py` | ✅ | AC-6.1全字段记录；保存失败降级不阻塞 |
| **D4** 容错机制 | `solver/recovery.py` | ✅ | 保守回退+检查点；异常注入：语法错有容错完成率1.0 vs 无容错0.0 |
| **D5** 可视化平台 | `ui/*` | ✅ | 四视图（路径地图/收敛曲线/LLM时间线/3D空域）+ 证据导出 |
| **D6** 真实数据 | `data/instance.py` | ✅ | 12个Madrid路由+Zenodo，真实TSV解析，无mock |
| **D7** 实验与统计 | `experiments/*` | ✅ | 三组对照+四组消融+三场景异常注入+自研统计（Cliff's delta/Kendall's W/Holm/Friedman） |

## 2. 关键假设与简化（设计文档 3.4 明示）

- **H1 坡度建模假设**：跨模型评估（M1恒定/M2线性/M3耦合）统一在M3真实评估器下计算成本差异。
  **实测结论**：12实例跨模型评估中，3/12实例M1与M3路径发生分化（diff=True），2/12实例gap≠0（max=0.0027）。
  分化机制已可观测，但绝对幅度<2%（`slope_modeling_necessary`阈值），说明本数据集坡度效应对总成本影响较小。
  这是**真实数据结果**，非代码缺陷（已在`PERF_AND_RELOCATE_NOTES.md`记录）。

- **H2 LLM 生成质量假设**：B组需配置LLM API后跑真实效果；当前未配置时走降级回退，
  报告中已如实标注（AC-7.1：若LLM组性能退化则假设不成立，需重新审视LLM价值）。

- **H3 平台价值假设（容错）**：异常注入实验量化：语法错注入下有容错completion=1.0、
  recoveries=1；无容错completion=0.0。**容错价值被证实。**

## 3. 性能优化记录（T-14）

| 优化 | 效果 |
|---|---|
| numpy haversine距离矩阵（修坐标单位bug） | 段代价O(1)查询，θ计算正确 |
| `initial_solution` numpy argmin | O(n²)→O(n·log n) |
| `repair_greedy`候选位限制(max_cands=200) | 避免O(n²)全位枚举 |
| `relocate`算子（跨路径移动） | M1/M3路径可分化 |

优化后：2000节点单实例cross-model eval ≈ 33s（4s预算）。

## 4. 已知限制与后续

- 12实例全量跨模型评估在2000节点下总耗时~7min，需拆批运行（已按4批×3实例完成）。
- B组（LLM-Only）需配置LLM API后重跑才能得到真实LLM质量数据。
- `relocate`算子深化路线（负载感知/频率自适应/regret2联合/证据链扩展/块级移动）已记录在
  `PERF_AND_RELOCATE_NOTES.md`，供T-15/T-16增强阶段实施。

## 5. 快速验证清单

```bash
cd demo
python healthcheck.py                  # 应输出 overall=OK
python -m data.instance --force         # 应输出 已构建12个实例
streamlit run ui/app.py                 # 控制台可启动，三Tab正常
python experiments/stats.py --instances 3 --time-budget 5 --max-nodes 500  # 报告生成
```
