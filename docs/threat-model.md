# 威胁模型

## 资产与信任边界

需要保护的资产包括 Provider 凭据、上传文档、未公开设备事实、run artifacts、历史案例
和 model/RAG provenance。信任边界位于 upload API、model gateway、RAG service、
领域 subprocess、SQLite store 和 artifact download endpoint。

## 主要威胁与控制措施

| 威胁 | 控制措施 | 剩余风险 |
|---|---|---|
| 凭据泄露 | 仅环境变量注入、HTTP failure 脱敏、secret scan | 曾分享的 key 仍需人工轮换 |
| Path traversal / 任意 artifact 读取 | 十六进制 run ID、上传扩展名 allowlist、resolved-path containment | 本地 operator 仍控制宿主机 |
| 超大或恶意上传 | 15 MiB 限制、隔离的解析 subprocess、timeout | PDF parser 漏洞仍需升级依赖或 sandbox |
| 论文/设备文档 Prompt Injection | 将 artifact 视为数据、evidence-only RAG prompt、deterministic check | 模型仍可能遵循对抗内容 |
| 跨 run 污染 | run-scoped path 和新的领域 subprocess | Provider/RAG quota 仍为全局共享 |
| 历史案例泄漏 | 将 episodic result 标记为 prior，并与目标证据隔离 | 不良 prompt 可能过度依赖 prior |
| 无依据的安全结论 | accepted-path linkage、Critic、citation、human gate | 评测质量依赖专家标签 |
| DoS / 成本耗尽 | 时间与 attempt 限制、token accounting、cancel、文件限制 | 强制 token 拒绝仍需 Provider streaming/token hook |

该 API 主要面向可信的本地演示环境。暴露到互联网前还需要 authentication、TLS、
per-user authorization、rate limit、malware scanning 和加固后的 container profile。
