# ADR 002: Separate episodic memory from literature RAG

- Status: Accepted
- Context: previous device cases are useful priors but cannot prove facts about
  a new target device.
- Decision: store cases and physical validation outcomes in SQLite; keep the
  existing paper RAG unchanged; label recalled cases as non-evidentiary priors.
- Consequences: confirmation/rejection signals improve ranking without leaking
  historical claims into target evidence. The two stores have independent
  lifecycle and evaluation metrics.
