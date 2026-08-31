# ADR 001：使用 subprocess 隔离领域阶段

- 状态：已接受
- 背景：领域阶段使用 module-level runtime 配置和 run-scoped artifacts，因此并发
  server request 需要明确的隔离边界。
- 决策：每个领域阶段都在新的 subprocess 中执行，并使用 run-scoped path 和
  environment；Harness 负责 supervision 和 checkpoint。
- 影响：并发 run 不会覆盖彼此的全局状态，阶段支持取消和超时。进程启动和 JSON
  artifact 会带来少量额外开销，但可以换取清晰的执行边界和故障隔离。
