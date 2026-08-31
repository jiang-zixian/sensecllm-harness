# SenseCLLM Harness

面向传感器与信息物理系统安全分析的物理约束多 Agent Harness。系统将机理图搜索、
约束推理、论文 RAG、可恢复 Agent 执行和历史案例记忆整合为统一架构。

![SenseCLLM Harness demo](docs/assets/sensecllm-demo.gif)

## 已实现能力

- 五个领域分析 Agent、案例召回/精排 Agent，以及独立的 Critic Agent
- 带类型化 run/stage 状态的 Supervisor
- JSON checkpoint、断点恢复和 JSONL 生命周期事件
- subprocess 隔离，以及每个 Agent 独立的 stdout/stderr 日志
- 基于 SQLite 的 Episodic Memory，保存设备、路径、漏洞、实验与物理验证结果
- 通过 ChatAnywhere DeepSeek 按需复核，并支持 revise/reject/human 路由
- 基于证据的报告问答，以及考虑验证反馈的历史案例排序
- CLI、FastAPI/SSE、浏览器仪表盘、运行对比、指标和 trace
- 仅通过本地环境配置敏感凭据

系统设计见[架构文档](docs/architecture.md)，完整实施清单见 [TODO](TODO.md)。
如果需要学习代码级 Agent 架构、逐 Agent 实现和 30 道项目面试题，请阅读
[面试学习手册](docs/interview-guide.md)。实测 smoke test 结果及其适用边界见
[评测结果](docs/evaluation-results.md)，Provider key 的安全处理方式见
[凭据轮换手册](docs/credential-rotation.md)。

## 安装与配置

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[api,legacy,rag,dev]'
cp .env.example .env
```

只需在 `.env` 中填写一次 `CHATANYWHERE_API_KEY` 和 `SILICONFLOW_API_KEY`。
CLI、API、领域 worker 和 Sensor RAG 都会自动加载这个被 Git 忽略的文件；
如果进程环境中显式设置了同名变量，则以进程环境为准。然后启动 RAG：

```bash
python -m sensor_rag serve
```

Harness 和 Critic 的默认模型都是 `deepseek-v3.2`，需要时可在 `.env` 中修改。
不要使用 `git add -f` 将 `.env` 强制提交到 Git。

运行一次分析：

```bash
sensecllm analyze /absolute/path/to/datasheet.pdf --model deepseek-v3.2

# 可复现的 Agent 消融实验
sensecllm analyze examples/demo_sensor.md --profile single_agent
sensecllm analyze examples/demo_sensor.md --profile no_memory
sensecllm analyze examples/demo_sensor.md --profile no_critic
```

恢复中断的运行：

```bash
sensecllm resume runs/<run-id>/checkpoint.json
sensecllm recover-stale --older-than-seconds 300
```

搜索历史案例并记录物理验证结果：

```bash
sensecllm memory-search microphone --mechanism nonlinearity
sensecllm record-verification <case-id> "Ultrasonic command injection" confirmed
```

可选的 API 服务：

```bash
uvicorn sensecllm.api.app:app --reload
```

打开 `http://127.0.0.1:8000/`，可使用文件上传、实时 Agent 状态、机理路径、
Memory 反馈、基于证据的报告问答和运行对比功能。

常用接口：

- `POST /v1/runs` — 启动分析
- `GET /v1/runs/{run_id}` — 查看 checkpoint 状态
- `GET /v1/runs/{run_id}/events` — 通过 SSE 流式获取生命周期事件
- `POST /v1/runs/{run_id}/cancel` — 终止正在运行的 Agent subprocess
- `POST /v1/runs/{run_id}/decision` — 对 gated run 执行 approve、revise 或 reject
- `POST /v1/runs/{run_id}/chat` — 针对报告发起带引用约束的问答
- `GET /v1/runs/{run_id}/artifacts/{name}` — 下载输出或 Agent 日志
- `GET /v1/memory/cases` — 搜索 Episodic Memory 中的设备案例
- `POST /v1/memory/cases/{case_id}/verification` — 记录物理验证结果
- `GET /metrics` — 获取 Prometheus 兼容的本地指标

完整实施清单见 [TODO.md](TODO.md)。

## Docker 演示环境

配置 Provider key 后，构建并启动 API 与 RAG 服务：

```bash
docker compose up --build
```

仓库中的 `examples/demo_sensor.md` 是虚构且可再分发的示例。可从宿主机启动分析：

```bash
curl -X POST http://127.0.0.1:8000/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{"input_path":"/app/examples/demo_sensor.md","model":"deepseek-v3.2"}'
```

首次执行完整检索前必须先构建 RAG 索引。Docker volume 会在服务重启之间保留
生成的 `.rag_index`。

## 安全说明

源码只使用系统运行所需的凭据，并通过环境变量提供。已经删除废弃的 key 字段。
任何曾经提交或分享过的凭据仍应由所有者主动轮换。在将本地演示 API 暴露到网络前，
请先阅读[威胁模型](docs/threat-model.md)。
