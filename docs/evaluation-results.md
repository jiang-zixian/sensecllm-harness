# 实测评估与消融结果

下列数值均来自 2026-08-25（Asia/Shanghai）的真实 Provider 调用。输入是可再分发的
synthetic 文件 `examples/demo_sensor.md`，因此这些数据只是工程 smoke/operational
结果，不能解释为通用模型准确率或统计显著提升。

## 六次运行的 Operational Ablation

| 配置 | RAG | Constraints | Critic | 时间（秒） | Tokens | 调用数 | Accepted paths |
|---|---:|---:|---:|---:|---:|---:|---:|
| 完整 Multi-Agent | on | on | on | 320.975 | 127,123 | 12 | 3 |
| Multi-Agent，不使用 Critic | on | on | off | 314.536 | 119,439 | 12 | 3 |
| Single Agent | on | on | off | 411.437 | 188,577 | 19 | 5 |
| Multi-Agent，不使用 RAG | off | on | off | 370.743 | 128,666 | 19 | 4 |
| Multi-Agent，不使用 constraints | on | off | off | 466.403 | 205,578 | 20 | 6 |
| Single Agent，不使用 RAG | off | on | off | 291.111 | 106,005 | 15 | 4 |

成对 operational 对比如下：

- multi-Agent vs single Agent：第 2、3 行（RAG/constraint/Critic 设置相同）；
- RAG vs no RAG：第 2、4 行；
- constraints vs no constraints：第 2、5 行；
- Critic vs no Critic：第 1、2 行。

由于每种配置只运行一次，并且 model sampling 与 Provider load 都可能变化，这些差异
只能作为观测结果，不能作为因果性能结论。原始数据位于
`evals/results/ablations.json`，生成的图位于 `evals/results/ablations.svg`。

## Metric Pipeline Smoke Report

为了验证 evaluator 管道，六个输出使用从一次已复核 synthetic run 中提取的
pseudo-reference 进行评分。`evals/results/ablation-evaluation-summary.json` 输出了
bootstrap interval，但它不能弥补缺少独立专家标签的问题。观测均值如下：

| 指标 | 均值 |
|---|---:|
| 传感器类型 Exact Match | 0.5000 |
| Evidence-support Precision | 0.8734 |
| Unsupported-claim Rate | 0.1266 |
| 实验 Constraint Pass Rate | 1.0000 |
| 机理 F1 | 0.8690 |
| 漏洞 F1 | 0.1667 |

较低的漏洞一致性反映了不同运行相对 pseudo-reference 在命名和内容上的明显变化。
该低分被如实保留。可发表结果必须使用领域专家提供的不可变标签。

## RAG Smoke Audit

RAG service 将 20 份真实 PDF 索引为 745 个 chunk，indexing failure 为 0。一次仅包含
一个 query、根据标题审核相关性的 audit 得到 Recall@5 1.000、MRR 1.000、NDCG@5
0.8921。该结果只验证 retrieval/evaluation 管道；judged pool 太小，不能用于研究结论。

## 真实模型 Gateway Probe

三种 ChatAnywhere 配置都返回了要求的严格 JSON schema：

| 模型 | 延迟（秒） | 已统计 Tokens |
|---|---:|---:|
| `deepseek-v3.2` | 3.804 | 78 |
| `deepseek-v3.2-thinking` | 4.769 | 136 |
| `deepseek-v4-flash` | 8.607 | 250 |

该 probe 比较的是 gateway/schema 行为，而不是最终任务质量。
