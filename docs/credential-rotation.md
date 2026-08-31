# Provider 凭据轮换手册

仓库中不包含 Provider 凭据。账户所有者于 2026-08-25 决定继续使用当前的
ChatAnywhere inference 凭据和 SiliconFlow embedding/reranking 凭据。因此，轮换是
可选的安全加固措施，而不是发布阻塞项；如果之后风险决策发生变化，可按本手册操作。

## 安全操作顺序

1. 在每个 Provider 的账户 dashboard 中创建替代 API key，暂时不要撤销当前可用 key。
2. 只在本地 secret manager 或未被 Git 跟踪的 `.env` 中保存替代 key：

   ```bash
   CHATANYWHERE_API_KEY=...
   SILICONFLOW_API_KEY=...
   ```

3. 打开一个新终端，避免复用此前 export 的值，然后独立验证替代 key：

   ```bash
   python -m sensor_rag check-api
   sensecllm analyze examples/demo_sensor.md --model deepseek-v3.2
   ```

4. 确认新 run 达到 `completed`，`usage.jsonl` 记录了真实调用，报告非空，并且 RAG
   返回带引用的来源。
5. 在两个 Provider dashboard 中撤销旧 key。
6. 再次执行简短 API probe。已撤销的旧 key 应认证失败，替代 key 应继续成功。
7. 从 shell profile、IDE run configuration、本地历史、CI variable、cloud secret store
   和所有私人副本中删除旧值。不要把任何 key 粘贴到 issue、commit、截图或聊天中。

## 仓库验证

轮换后运行仓库中的扫描器：

```bash
python scripts/check_secrets.py
git status --short
```

第一条命令必须报告未发现嵌入的 Provider 凭据，第二条命令不能显示 `.env` 或其他
凭据文件。扫描器也会检查残留 Python bytecode 中的明文 bearer credential。它有意
排除 `runs/`；如果 run artifacts 曾被对外分享，即使 Harness 不记录 API key，也应
单独审计或删除这些副本。

## 回滚

如果替代 key 在旧 key 撤销前验证失败，可临时恢复此前的环境变量，检查 Provider
permission、quota 和 model access；替代 key 验证通过前不要撤销旧 key。旧 key 一旦
撤销，回滚方式是再创建一个新 key，而不是重新引入可能已经暴露的凭据。
