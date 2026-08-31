# SenseCLLM 评测说明

`benchmark.example.json` 展示了带版本的标签格式。真实测试标签应经过人工审核；一旦
基于这些标签报告结果，就应保持标签不可变。

评测一个已完成的 run：

```bash
sensecllm evaluate-run runs/<run-id>/checkpoint.json evals/cases/<case-id>.json
```

该命令会输出抽取字段 F1、机理与漏洞 PR/F1、evidence-support precision、
unsupported-claim rate、实验 constraint pass rate、物理路径数量、Critic decision、
attempts、retries、tokens 和运行时间。

RAG Recall@K、MRR 和 NDCG 通过以下命令评测：

```bash
python scripts/evaluate_rag.py evals/rag_judgments.example.json --k 5
```

示例 judgment 被有意留空。报告准确率前必须整理并冻结专家标签；synthetic smoke test
不能作为独立 benchmark 对外表述。
