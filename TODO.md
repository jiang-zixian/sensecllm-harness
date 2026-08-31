# SenseCLLM Harness 实施清单

本清单按照演示效果和简历价值排序。勾选的条目必须已有代码实现和与风险相称的验证；
任何 benchmark 提升结论都必须基于已提交的评测数据，否则不能视为完成。

## 阶段 0 —— 仓库与运行基础

- [x] 增加 Python packaging、CLI 入口、配置模板和 README。
- [x] 删除源码中嵌入的 API 凭据和本机绝对路径。
- [x] 将五阶段物理/RAG 分析组织为领域 Agent。
- [x] 增加类型化 run/stage 状态、JSON checkpoint/resume 和 JSONL 生命周期事件。
- [x] 增加 SQLite Episodic Memory 和物理验证反馈。
- [x] 增加单元测试、Ruff、MyPy 和 import smoke test。
- [x] 处理源码和历史中曾出现的凭据：仓库与残留 bytecode 已清理；账户所有者于
  2026-08-25 明确接受继续使用当前 ChatAnywhere 与 SiliconFlow key。

  风险说明：由于无法证明凭据从未暴露，轮换仍是更安全的做法。当前 key 保持在 Git
  之外，只通过本地环境注入；但轮换不再是项目完成的必要条件。

## 阶段 1 —— 具备生产安全语义的 Harness runtime

- [x] 在独立 subprocess 中执行每个领域阶段。
- [x] 支持多个 run，避免全局配置跨 run 污染。
- [x] 持久化每个 Agent 的 stdout/stderr，并暴露日志 artifact 路径。
- [x] 增加优雅取消和每 Agent timeout 控制。
- [x] 增加 retry policy、backoff 和 failure classification。
- [x] 增加 run 级时间、Agent attempt、模型 token 和可配置 cost budget。
- [x] 增加生命周期事件和 Agent 进度的 SSE 接口。
- [x] 增加 artifact 下载和 run 列表接口。
- [x] 增加进程重启后的 stale-running checkpoint 恢复。

## 阶段 2 —— Agent 智能与 Memory

- [x] 在文档抽取后增加 `CaseRecallAgent`。
- [x] 按设备型号和传感器类型召回相似历史案例。
- [x] 使用组件与机理重合度改进历史案例排序。
- [x] 保证历史案例只是 prior，而不是目标设备证据。
- [x] 在漏洞生成后增加独立的 deterministic `CriticAgent`。
- [x] 配置可用时，通过 ChatAnywhere 将不一致结论升级给 DeepSeek 复核。
- [x] 增加条件式 revise/reject/human-review 路由。
- [x] 持久化 Critic 决策及 model/prompt 版本。
- [x] 增加人工 approve/reject/revise 接口和修正后重跑。
- [x] 将 confirmed/rejected 物理结果反馈到 Episodic Memory 排序。
- [x] 增加简单的 per-run Conversation Memory 和基于证据的报告问答。

## 阶段 3 —— 评测与算法实验

- [x] 定义带版本的 benchmark case schema 和 train/dev/test 划分。
- [x] 增加抽取字段 F1 评测。
- [x] 增加 RAG Recall@K、MRR 和 NDCG 评测。
- [x] 增加 evidence-support precision 和 unsupported-claim rate。
- [x] 根据 accepted paths 计算机理标签 precision/recall/F1（edge-level validity 待完善）。
- [x] 使用专家标签计算漏洞 precision/recall。
- [x] 增加实验参数 constraint pass rate。
- [x] 跟踪执行时间、Agent attempts、retries、failure class、tokens 和 configured cost。
- [x] 在 synthetic demo 上运行 single-agent 与 multi-agent operational ablation。
- [x] 运行 RAG/no-RAG、constraints/no-constraints、Critic/no-Critic 消融。
- [x] 至少比较两种模型配置，不虚构业务指标。
- [x] 生成带 confidence interval 的可复现评测报告。

## 阶段 4 —— 可观测性与演示产品

- [x] 增加结构化 trace/span schema 和请求 correlation ID。
- [x] 增加本地 metrics 接口和可选 OTLP export hook。
- [x] 构建用于上传、实时 Agent graph、证据和报告查看的 Web UI。
- [x] 可视化 accepted/unresolved/rejected 物理机理路径。
- [x] 增加案例 Memory 浏览器和验证结果编辑器。
- [x] 增加 model/prompt/RAG 配置的 run comparison。
- [x] 为 API 和 RAG 增加 Dockerfile 与 Docker Compose（独立 UI service 待完善）。
- [x] 增加 health probe 和示例配置。

## 阶段 5 —— 质量、发布与实习展示

- [x] 增加 unit、integration、API、subprocess 和 failure-injection tests。
- [x] 增加执行 lint、type check、test 和基础 secret scanning 的 GitHub Actions。
- [x] 使用小而可解释的 commit 初始化 Git 历史。
- [x] 增加 Architecture Decision Record 和 threat model。
- [x] 使用可再分发的 synthetic sample document 搭建 Docker demo 环境。
- [x] 录制简短 demo GIF。
- [x] 发布带适用范围限制的 smoke/evaluation 表格和 ablation plot。
- [x] 只使用实测结果和明确范围限制编写简历 bullet。
- [x] 准备架构讲解、STAR 话术和常见面试追问。
