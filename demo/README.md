# SDVRPD LLM 驱动 ALNS 求解器原型

> 坡地无人机协同车辆路径问题（Slope-dependent DRPVD）的 LLM 辅助自适应大邻域搜索（ALNS）原型。
> 本目录为可运行的原型交付物（设计文档 D1–D7 全部覆盖）。

## 目录结构

```
demo/
├── healthcheck.py          # 启动健康检查（FR-21）
├── requirements.txt        # 锁定 7 个依赖版本（conda sdvrpd / Python 3.11）
├── PERF_AND_RELOCATE_NOTES.md  # T-14 性能优化 + relocate 深化路线
├── config/
│   └── params.json         # 能耗/时间窗/惩罚系数集中配置（AC-8.3）
├── data/
│   ├── instance.py         # 数据层：TSV 嗅探 + 流式采样 + 坡度计算 + 实例 JSON
│   └── instances/          # 12 个 SDVRPD 实例 JSON（程序生成）
├── solver/
│   ├── model.py            # SDVRPD 建模：MILP 形式化 + 卡车/无人机能耗函数
│   ├── alns.py             # 自研 ALNS（初始解/轮盘赌/贪心+Regret-2/退火/检查点/relocate）
│   └── recovery.py         # 保守回退 + 检查点恢复（FR-8/FR-9）
├── llm/
│   ├── prompt.py           # 实例特征 + 破坏算子提示词
│   ├── generate.py         # LLM 调用 + 代码解析 + 预置算子回退
│   ├── static_check.py     # 静态检查器（签名/禁止模式/语法）
│   └── closed_loop.py      # LLM 生成闭环（重试 + 回退 + 证据记录）
├── verify/
│   ├── evidence.py         # 证据链保存（AC-6.1 全字段）
│   ├── metrics.py          # 评估指标（gap/feasibility/improvement）
│   └── cross_eval.py       # 跨模型评估器（M1/M2/M3 → 统一真实评估器）
├── experiments/
│   ├── run_all.py          # 三组对照（A/B/C × 15 种子）
│   ├── ablation.py         # 四组消融（去LLM/去耦合/去容错/去自适应）
│   ├── anomaly.py          # 三种异常注入（语法错/接口不匹配/超时10%）
│   ├── stats.py            # 统计检验 + 报告（自研 Cliff's delta/Kendall's W/Holm/Friedman）
│   └── results/            # 实验结果 JSON + 图表
├── ui/
│   ├── app.py              # Streamlit 控制台（配置/求解/可视化 Tab）
│   ├── config_tab.py       # LLM API 配置页
│   └── dashboard.py        # 四视图（路径地图/收敛曲线/LLM时间线/3D空域）+ 证据导出
├── evidence/               # 证据记录 JSON（iter_*.json / rounds/）
└── checkpoints/            # ALNS 检查点（ckpt_<instance>.json）
```

## 快速启动

```bash
# 1. 激活 conda 环境
conda activate sdvrpd   # 或 D:\software\anaconda\envs\sdvrpd

# 2. 安装依赖（如尚未安装）
pip install -r demo/requirements.txt
pip check                 # 应输出 "No broken requirements found"

# 3. 构建 12 个 SDVRPD 实例（从真实数据）
cd demo
python -m data.instance --force
# 输出：已构建 12 个实例到 data/instances/

# 4. 健康检查（FR-21）
python healthcheck.py
# 应输出 overall=OK, data_files=12

# 5. 单次 ALNS 求解（验证 D1）
python -c "
import json, glob, sys
sys.path.insert(0, '.')
from solver.alns import ALNSSolver
from solver.model import load_params
inst = json.load(open(sorted(glob.glob('data/instances/*.json'))[0], encoding='utf-8'))
out = ALNSSolver(inst, params=load_params(), seed=1, time_budget=10).run()
print('objective:', out['objective_value'], 'feas:', out['feasibility_rate'])
"
```

## LLM 配置（D2）

通过 Streamlit 配置页写入 `config/llm_config.json`：

```bash
streamlit run demo/ui/app.py
# 切换到「配置」Tab → 填写 API key / base URL / model → 测试连接 → 保存
```

无 LLM 配置时，所有模块自动降级到预置算子（AC-4.3），不崩溃。

## 跨模型 H1 验证（FR-20 / AC-7.2）

```bash
# 12 实例全量跨模型评估（T-14 性能优化后，每实例 ~33s，总 ~7 min）
cd demo
python -c "
import json, glob, sys
sys.path.insert(0, '.')
from verify.cross_eval import cross_model_eval
from solver.model import load_params
for fp in sorted(glob.glob('data/instances/*.json')):
    inst = json.load(open(fp, encoding='utf-8'))
    rep = cross_model_eval(inst, params=load_params(), seed=1, time_budget=3.0)
    print(inst['instance_id'], 'gap=', rep['gap_M1_vs_M3'])
"
```

结果已缓存在 `experiments/results/cross_model_12instances.json`。

## 统计与报告（FR-16/17 / AC-7.4/7.5）

```bash
cd demo
python experiments/stats.py --instances 12 --time-budget 5
# 输出：experiments/results/report.json + 图表
```

## 可视化与证据导出（D5）

```bash
streamlit run demo/ui/app.py
# 切换到「可视化」Tab：四视图（路径地图/收敛曲线/LLM时间线/3D空域）
# 底部「证据导出」：全量 + 按 run_id 导出 JSON
```

## 关键性能优化（T-14）

| 优化 | 效果 |
|---|---|
| numpy haversine 距离矩阵（修坐标单位 bug） | 段代价 O(1) 查询 |
| `initial_solution` numpy argmin | O(n²)→O(n·log n) |
| `repair_greedy` 候选位限制（max_cands=200） | 避免 O(n²) 全位枚举 |
| `relocate` 算子（跨路径移动，方案二） | M1/M3 路径可分化 |

优化后：2000 节点单实例 cross-model eval ≈ 33s（预算 4s）。

## 已知限制

- B 组（LLM-Only）需配置 LLM API 后才能反映真实 LLM 质量；未配置时走降级回退。
- 12 实例全量跨模型评估在 2000 节点下总耗时 ~7 min，超出单条命令限制时建议拆 4 批 × 3 实例运行。
