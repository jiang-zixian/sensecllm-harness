# 三分钟演示脚本

1. 启动 RAG 和 API，打开 `http://127.0.0.1:8000/`。
2. 上传 `examples/demo_sensor.md`，展示实时 Agent graph。
3. 打开机理路径，区分 accepted/unresolved/rejected 分支。
4. 展示 Critic decision、prompt/model 版本、trace span 和 token usage。
5. 如果进入 gated 状态，执行 revise 或 approve，并从同一个 checkpoint 恢复。
6. 打开最终报告，提出一个证据问题并检查 citations。
7. 记录物理验证结果，重新运行并展示它对案例排序的影响。
8. 对比两个 run，同时明确区分 smoke/operational metrics 与专家审核的 benchmark accuracy。
