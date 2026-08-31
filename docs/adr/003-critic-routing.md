# ADR 003：Deterministic-first Critic 路由

- 状态：已接受
- 决策：先在本地检查 graph support 和 component/mechanism 一致性，只对不一致情况
  调用 DeepSeek。持久化 prompt/model 版本，并路由到 approve、schema-normalized
  revise、reject 或 human review。
- 影响：明确通过的情况无需额外模型调用；不确定的修订仍然可审计；人工修正后必须
  重新运行 Critic，才能进入下游阶段。
