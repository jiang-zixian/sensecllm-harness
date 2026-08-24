# Resume bullets (measured and defensible)

Use one or two bullets and keep the scope qualifier when discussing results.

- Refactored a sensor-security research pipeline into an 8-Agent Harness with
  subprocess isolation, JSON checkpoint/resume, SSE, retries/cancellation,
  token budgets, structured traces, SQLite episodic memory, and Critic-driven
  revise/reject/human-review routing; completed a real DeepSeek E2E smoke run in
  320.975 s with 12 model calls and 127,123 accounted tokens.
- Integrated the retained hybrid paper RAG without duplicating its core,
  indexing 20 PDFs into 745 chunks with 0 indexing failures; a one-query,
  title-reviewed plumbing audit measured Recall@5 1.00, MRR 1.00, and NDCG@5
  0.892 (explicitly not an expert accuracy benchmark).
- Built an evaluation and demo layer covering extraction/label PR-F1,
  evidence support, unsupported claims, experiment constraints, RAG ranking,
  bootstrap confidence intervals, real-run ablations, a FastAPI/SSE dashboard,
  grounded report chat, Prometheus metrics, Docker, CI, and secret scanning.
- Compared three live ChatAnywhere configurations on a strict-JSON gateway
  probe: all 3 returned the required schema; observed latencies were 3.804 s
  (`deepseek-v3.2`), 4.769 s (`deepseek-v3.2-thinking`), and 8.607 s
  (`deepseek-v4-flash`) on that single probe only.

Do not convert the synthetic smoke labels or the single-query RAG audit into a
general accuracy/improvement claim. Replace them with immutable expert-reviewed
test data before claiming model quality gains.
