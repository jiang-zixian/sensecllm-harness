# Measured evaluation and ablation results

All values below were produced by real provider calls on 2026-08-25 (Asia/Shanghai).
The input is the redistributable synthetic `examples/demo_sensor.md`; therefore
these are engineering smoke/operational results, not a claim of general model
accuracy or statistical improvement.

## Six-run operational ablation

| Configuration | RAG | Constraints | Critic | Time (s) | Tokens | Calls | Accepted paths |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full multi-Agent | on | on | on | 320.975 | 127,123 | 12 | 3 |
| Multi-Agent, no Critic | on | on | off | 314.536 | 119,439 | 12 | 3 |
| Single Agent | on | on | off | 411.437 | 188,577 | 19 | 5 |
| Multi-Agent, no RAG | off | on | off | 370.743 | 128,666 | 19 | 4 |
| Multi-Agent, no constraints | on | off | off | 466.403 | 205,578 | 20 | 6 |
| Single Agent, no RAG | off | on | off | 291.111 | 106,005 | 15 | 4 |

The paired operational comparisons are:

- multi-Agent vs single Agent: rows 2 and 3 (same RAG/constraint/Critic settings);
- RAG vs no RAG: rows 2 and 4;
- constraints vs no constraints: rows 2 and 5;
- Critic vs no Critic: rows 1 and 2.

Because each configuration was run once and model sampling/provider load can
vary, differences are observations, not causal performance claims. Raw data is
in `evals/results/ablations.json`; the generated plot is
`evals/results/ablations.svg`.

## Metric-pipeline smoke report

The six outputs were scored against a pseudo-reference derived from one reviewed
synthetic run solely to exercise the evaluator. Bootstrap intervals are emitted
by `evals/results/ablation-evaluation-summary.json`; they do not compensate for
the lack of independent expert labels. Mean observed values were:

| Metric | Mean |
|---|---:|
| Sensor type exact match | 0.5000 |
| Evidence-support precision | 0.8734 |
| Unsupported-claim rate | 0.1266 |
| Experiment constraint pass rate | 1.0000 |
| Mechanism F1 | 0.8690 |
| Vulnerability F1 | 0.1667 |

The low vulnerability agreement reflects highly variable naming/content against
the pseudo-reference and is retained rather than hidden. A publishable result
requires immutable labels from domain experts.

## RAG smoke audit

The RAG service indexed 20 real PDFs into 745 chunks with zero indexing
failures. A one-query title-reviewed relevance audit measured Recall@5 1.000,
MRR 1.000, and NDCG@5 0.8921. This validates retrieval/evaluation plumbing only;
the judged pool is too small for a research claim.

## Live model gateway probe

All three ChatAnywhere configurations returned the requested strict JSON schema:

| Model | Latency (s) | Accounted tokens |
|---|---:|---:|
| `deepseek-v3.2` | 3.804 | 78 |
| `deepseek-v3.2-thinking` | 4.769 | 136 |
| `deepseek-v4-flash` | 8.607 | 250 |

This probe compares gateway/schema behavior, not end-task quality.
