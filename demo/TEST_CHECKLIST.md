# 队员手动测试项表格

> 覆盖设计文档 D1–D7、SPEC FR/AC/NFR 和 demo 实际入口。每项均为可直接人工执行的测试。
> 测试前请先完成 README 的环境准备（conda 激活 + 依赖安装 + 实例构建）。

## 一、环境依赖（NFR-4 / T-01）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T01-1 | 依赖安装 | `pip install -r requirements.txt` | 无失败 | □ | |
| T01-2 | 依赖零冲突 | `pip check` | 输出 "No broken requirements found" | □ | |
| T01-3 | 关键包可导入 | `python -c "import numpy,pandas,scipy,matplotlib,plotly,streamlit,requests"` | 打印 ok | □ | |

## 二、健康检查与启动（FR-21 / AC-10）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T02-1 | 启动健康检查 | `python healthcheck.py` | overall=OK，data_files=12 | □ | |
| T02-2 | 模块故障隔离 | 临时移走一个数据文件，重跑 `healthcheck.py` | 该实例标记不可用，其余正常，项目不崩溃 | □ | |

## 三、数据层（FR-1 / D6 / AC-1.1）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T03-1 | 实例生成 | `python -m data.instance --force` | 输出"已构建 12 个实例"，data/instances/ 下 12 个 JSON | □ | |
| T03-2 | 实例字段完整 | 随机抽查 1 个 JSON | 含 instance_id、nodes、arcs(theta)、demands、time_windows、truck_types、drones、energy_params | □ | |
| T03-3 | 坡度手算核对 | 取一段 Δh 与 d，手算 θ=arctan(Δh/d) | 与 JSON 中该弧 theta 一致 | □ | |
| T03-4 | 真实数据确认 | 查看代码或文档 | 数据来源为 Madrid 12 CSV + Zenodo，无模拟数据 | □ | |

## 四、建模正确性（FR-2 / D1 / AC-2）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T04-1 | 卡车能耗随坡度增大 | 调用 `truck_energy` 对比 θ=0.1 与 θ=0.3 同距离同载重 | θ 大者返回值更大 | □ | |
| T04-2 | 卡车能耗随载荷线性放大 | 调用 `truck_energy` 对比 u=0 与 u=Q | u=Q 者返回值更大 | □ | |
| T04-3 | 无人机三段能耗 | 调用 `drone_energy` | 返回 dict 含 cruise/climb/vertical/total 四分量 | □ | |
| T04-4 | 无人机续航超限判不可行 | 构造能耗值超 `η·Bmax` 的调用 | `drone_feasible` 返回 False | □ | |

## 五、ALNS 求解（FR-3 / FR-4 / AC-3）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T05-1 | 单实例可求解 | README 中的求解命令（time_budget=10） | 输出 objective_value + feasibility_rate（feas≈1.0） | □ | |
| T05-2 | 可复现 | 固定 seed 跑两次 | 两次 objective_value 一致 | □ | |
| T05-3 | 检查点恢复 | 跑 100 迭代后中断，再从 checkpoint 继续 | 迭代数连续，不重置 | □ | |
| T05-4 | 预置算子覆盖 | 查看 `solver/alns.py` 中 PREDEFINED_DESTROY | 含 random/worst/shaw 三类 | □ | |

## 六、证据链（FR-10 / D3 / AC-6.1）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T06-1 | 证据 JSON 落盘 | 完成一次运行后查看 evidence/ | 有 iter_*.json 生成 | □ | |
| T06-2 | 证据字段完整 | 打开任一证据 JSON | 含 iteration_id/timestamp/llm_prompt_hash/generated_code/static_check/execution/recovery_action 全字段 | □ | |
| T06-3 | 证据保存失败降级 | 模拟磁盘不可写（如读-only 环境） | 记录警告，主循环继续 | □ | |

## 七、LLM 生成闭环（FR-5/6/7 / D2 / AC-4）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T07-1 | 静态检查单测 | `python -m unittest llm.static_check -v` | 7/7 通过 | □ | |
| T07-2 | 合法算子通过 | 喂合法 destroy 函数 | passed=true | □ | |
| T07-3 | 禁止模式拦截 | 喂含 `open(`/`import requests`/语法错误的代码 | 被拦截，报告具体原因 | □ | |
| T07-4 | 无 LLM 配置降级 | 清空/删除 `config/llm_config.json` 后跑求解 | 自动走预置算子，不崩溃，recovery_action=predefined_fallback | □ | |
| T07-5 | 重试与回退 | 模拟 LLM 连续 3 次返回坏码 | 重试计数正确，第 3 次后回退预置算子，主循环不中断 | □ | |
| T07-6 | 配置页保存 | 在 Streamlit 配置 Tab 填写 API 参数 | llm_config.json 更新，求解器可读 | □ | |

## 八、保守回退与检查点（FR-8/9 / D4）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T08-1 | 不可行保守回退 | 构造强约束实例触发回退 | 未服务客户被标记并计入惩罚，目标值含惩罚项 | □ | |
| T08-2 | 检查点恢复 | 超时/中断后恢复 | 从断点继续，不重头 | □ | |

## 九、三组对照实验（FR-12 / D7 / AC-7.1）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T09-1 | 单实例三组 | `python experiments/run_all.py --instance IT_HIGH --time-budget 60` | A/B/C 三组各出结果 JSON | □ | |
| T09-2 | 批量多实例 | `python experiments/run_all.py --all --seeds 15`（或 3 实例缩小验证） | 每实例三组结果齐全 | □ | |
| T09-3 | 统计报告 | `python experiments/stats.py --results evidence/ --output report.json` | 输出含 A/B/C 配对 Wilcoxon+Holm p 值、Friedman、Cliff's delta/Kendall's W | □ | |
| T09-4 | B 组未配置标注 | 未配置 LLM API 时跑 B 组 | 报告中如实标注 B 组走降级回退 | □ | |

## 十、消融与异常注入（FR-13 / D7 / AC-7.3 / H3）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T10-1 | 去 LLM 消融 | `python experiments/ablation.py --ablation no_llm` | 跑通并出差异 | □ | |
| T10-2 | 去耦合消融 | `python experiments/ablation.py --ablation no_coupling` | 跑通并出差异 | □ | |
| T10-3 | 去容错消融 | `python experiments/ablation.py --ablation no_fault_tolerance` | 跑通并出差异 | □ | |
| T10-4 | 去自适应权重 | `python experiments/ablation.py --ablation no_adaptive` | 跑通并出差异 | □ | |
| T10-5 | 语法错注入 | `python experiments/anomaly.py --scenario syntax --n 10` | 有容错 completion=1.0、recoveries≥1；无容错 completion=0.0 | □ | |
| T10-6 | 接口不匹配注入 | `python experiments/anomaly.py --scenario interface --n 10` | 有/无容错差异被统计 | □ | |
| T10-7 | 超时注入 | `python experiments/anomaly.py --scenario timeout --n 10` | 有/无容错差异被统计（检查点恢复有效） | □ | |

## 十一、跨模型评估（FR-20 / D4 / AC-7.2 / H1）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T11-1 | 跨模型成本对比 | `cross_model_eval`（README 命令，可先 1 实例） | 输出 M1/M2/M3 在统一评估器下的成本对比 + gap | □ | |
| T11-2 | 12 实例全量 | 12 实例分 4 批运行（每批 3 实例） | 3/12 路径分化，max gap≈0.0027（记录于 PERFORMANCE_NOTES） | □ | |

## 十二、可视化与导出（FR-16/22 / D5/D7 / AC-9.1）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T12-1 | 控制台启动 | `streamlit run ui/app.py` | 三 Tab（配置/求解/可视化）正常 | □ | |
| T12-2 | 四视图渲染 | 进入「可视化」Tab | 路径地图/收敛曲线+算子热力/LLM 时间线/3D 空域 均渲染，数据与 evidence 一致 | □ | |
| T12-3 | 证据导出 | 点击「证据导出」（全量 + 按 run_id） | 生成可提交的记录包（JSON+图表+时间线） | □ | |

## 十三、系统自检（AC-10）
| 编号 | 测试项 | 执行步骤 | 通过标准 | 结果 | 备注 |
|---|---|---|---|---|---|
| T13-1 | 从零到启动 | 按 README 完整走一遍 | 项目正确启动并输出健康检查报告 | □ | |
| T13-2 | 单模块错不阻塞 | 人为致某模块报错后启动 | 该模块标记不可用，其余正常，整体不崩溃 | □ | |
