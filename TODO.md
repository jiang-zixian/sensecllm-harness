# SenseCLLM Harness roadmap

This roadmap is ordered by demo and resume value. A checked item must have code
and proportionate verification; benchmark improvement claims remain unchecked
until measured on committed evaluation data.

## Phase 0 — repository and compatibility foundation

- [x] Add Python packaging, CLI entry point, configuration template, and README.
- [x] Remove embedded API credentials and machine-local paths from source.
- [x] Wrap the unchanged five-stage physics/RAG pipeline as domain Agents.
- [x] Add typed run/stage state, JSON checkpoint/resume, and JSONL lifecycle events.
- [x] Add SQLite Episodic Memory and physical verification feedback.
- [x] Add unit tests, Ruff, MyPy, and import smoke tests.
- [ ] Rotate every credential that previously appeared in source or shared history. (Manual)

## Phase 1 — production-safe Harness runtime

- [x] Execute each legacy stage in an isolated subprocess.
- [x] Allow multiple runs without cross-run global configuration contamination.
- [x] Persist stdout/stderr per Agent and expose log artifact paths.
- [x] Add graceful cancellation and per-Agent timeout controls.
- [x] Add retry policy, backoff, and failure classification.
- [x] Add run-level time and Agent-attempt budgets (model-token accounting pending).
- [x] Add SSE endpoints for lifecycle events and Agent progress.
- [x] Add artifact download and run listing endpoints.
- [x] Add stale-running checkpoint recovery after process restart.

## Phase 2 — Agent intelligence and memory

- [x] Add `CaseRecallAgent` after document extraction.
- [x] Retrieve similar historical cases by model and sensor type.
- [x] Improve historical-case ranking with component and mechanism overlap.
- [x] Preserve the rule that historical cases are priors, not target evidence.
- [x] Add independent deterministic `CriticAgent` after vulnerability generation.
- [x] Escalate inconsistent findings to a DeepSeek review through ChatAnywhere when configured.
- [ ] Add conditional revise/reject/human-review routing.
- [ ] Persist Critic decisions and model/prompt versions.
- [x] Add human approve/reject endpoints for Critic-gated runs (correction flow pending).
- [ ] Feed confirmed/rejected physical results back into episodic case ranking.
- [ ] Add simple per-run conversation memory and evidence-backed report chat.

## Phase 3 — evaluation and algorithm experiments

- [x] Define a versioned benchmark case schema and train/dev/test split.
- [ ] Add extraction field F1 evaluation.
- [ ] Add RAG Recall@K, MRR, and NDCG evaluation using the existing RAG.
- [ ] Add evidence-support precision and unsupported-claim rate.
- [x] Add mechanism-label precision/recall/F1 from accepted paths (edge-level validity pending).
- [x] Add vulnerability precision/recall with expert labels.
- [ ] Add experiment-parameter constraint pass rate.
- [x] Track execution time, Agent attempts, retries, and failure class (tokens/cost pending).
- [ ] Run single-agent vs multi-agent ablation.
- [ ] Run RAG/no-RAG, constraints/no-constraints, and Critic/no-Critic ablations.
- [ ] Compare at least two model configurations without fabricating business metrics.
- [ ] Generate a reproducible evaluation report with confidence intervals.

## Phase 4 — observability and demo product

- [ ] Add structured trace/span schema and request correlation IDs.
- [ ] Add local metrics endpoint and optional OpenTelemetry/Langfuse export.
- [ ] Build a small web UI for upload, live Agent graph, evidence, and report inspection.
- [ ] Visualise accepted/unresolved/rejected physical mechanism paths.
- [ ] Add case-memory browser and verification-result editor.
- [ ] Add run comparison for model/prompt/RAG configurations.
- [x] Add Dockerfile and Docker Compose for API and RAG (UI service pending).
- [x] Add health probes and example configuration.

## Phase 5 — quality, release, and internship presentation

- [ ] Add unit, integration, API, subprocess, and failure-injection tests.
- [x] Add GitHub Actions for lint, type check, test, and basic secret scanning.
- [ ] Initialise Git history with small, explainable commits.
- [ ] Add architecture decision records and threat model.
- [x] Add a Docker demo foundation with a redistributable synthetic sample document.
- [ ] Record a short demo video/GIF.
- [ ] Publish measured benchmark tables and ablation plots.
- [ ] Write resume bullets using only measured results.
- [ ] Prepare architecture walkthrough, STAR story, and likely interview follow-ups.
