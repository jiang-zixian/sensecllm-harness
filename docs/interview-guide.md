# Interview walkthrough

## Two-minute architecture story

SenseCLLM keeps a physics-constrained sensor-security pipeline as the domain
core and wraps it in a production-style Agent Harness. A supervisor runs each
stage in an isolated subprocess, persists typed checkpoints/events/traces, and
supports retry, cancellation, budgets, and resume. Paper RAG provides cited
external evidence; SQLite episodic memory recalls validated device cases as
priors. A deterministic-first Critic validates that proposed vulnerabilities
are supported by accepted physical paths and escalates uncertain cases to
DeepSeek or a human.

## STAR story

- Situation: the research prototype depended on globals, embedded credentials,
  and a linear script, making concurrent use and failure recovery unsafe.
- Task: turn it into a demonstrable multi-Agent system without rewriting the
  domain algorithms or duplicating RAG.
- Action: introduced subprocess isolation, checkpointed orchestration, episodic
  feedback, Critic routing, observability, evaluation schemas, API/SSE, and UI.
- Result: cite only the measured values in `evals/results/` and the real E2E
  validation record; do not present synthetic smoke labels as expert accuracy.

## Likely follow-ups

1. Why not LangGraph? The custom supervisor makes checkpoint/failure semantics
   explicit and shows the underlying harness design; migration remains possible.
2. Why SQLite memory? It is inspectable, transactional, portable, and sufficient
   for a local case corpus; vector retrieval can be added after measured need.
3. How is hallucination controlled? Target facts and literature evidence have
   different provenance; graph constraints, a Critic, citations, and human gates
   provide layered controls rather than claiming elimination.
4. What would production require? Auth/RBAC, queue workers, Postgres/object
   storage, distributed tracing, rate limits, hardened parsing, and expert evals.
5. What failed in real testing? Critic revisions used schema aliases; canonical
   normalisation was added, which is an example of why typed boundaries matter.
