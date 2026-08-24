# SenseCLLM evaluation

`benchmark.example.json` documents the versioned label format. Real test labels
should be reviewed manually and kept immutable once results are reported.

Evaluate one completed run:

```bash
sensecllm evaluate-run runs/<run-id>/checkpoint.json evals/cases/<case-id>.json
```

The command reports extraction field F1, mechanism and vulnerability PR/F1,
evidence-support precision, unsupported-claim rate, experiment constraint pass
rate, physical-path counts, Critic decision, attempts, retries, tokens, and time.

RAG Recall@K, MRR, and NDCG are integrated with the existing RAG:

```bash
python scripts/evaluate_rag.py evals/rag_judgments.example.json --k 5
```

The example judgments are deliberately empty. Curate and freeze expert labels
before reporting accuracy; synthetic smoke tests must not be presented as an
independent benchmark.
