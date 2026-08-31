# 简历表述（基于实测、可解释）

建议选择其中一到两条使用；描述结果时必须保留适用范围说明。

- 设计并实现面向传感器安全分析的 8-Agent Harness，包含 subprocess isolation、JSON
  checkpoint/resume、SSE、retry/cancellation、token budget、structured trace、SQLite
  Episodic Memory，以及由 Critic 驱动的 revise/reject/human-review 路由；真实 DeepSeek
  E2E smoke run 用时 320.975 秒，完成 12 次模型调用并统计 127,123 tokens。
- 构建统一的 hybrid paper RAG 集成和单一检索服务，将 20 份 PDF 索引为 745 个 chunk，
  indexing failure 为 0；一次单 query、基于标题审核的管道 audit 得到 Recall@5 1.00、
  MRR 1.00、NDCG@5 0.892（明确不作为专家准确率 benchmark）。
- 构建评测和演示层，覆盖 extraction/label PR-F1、evidence support、unsupported claim、
  experiment constraint、RAG ranking、bootstrap confidence interval、真实 run 消融、
  FastAPI/SSE dashboard、grounded report chat、Prometheus metrics、Docker、CI 和 secret scanning。
- 使用 strict-JSON gateway probe 比较三种真实 ChatAnywhere 配置：三者均返回要求的
  schema；在该单次 probe 中，`deepseek-v3.2`、`deepseek-v3.2-thinking` 和
  `deepseek-v4-flash` 的观测延迟分别为 3.804、4.769 和 8.607 秒。

不要把 synthetic smoke label 或 single-query RAG audit 表述为通用准确率或提升结论。
在声称模型质量提升前，必须改用经过专家审核且不可变的测试数据。
