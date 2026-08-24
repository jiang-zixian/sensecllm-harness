# ADR 003: Deterministic-first Critic routing

- Status: Accepted
- Decision: check graph support and component/mechanism consistency locally,
  then use DeepSeek only for inconsistent cases. Persist prompt/model versions
  and route to approve, schema-normalised revise, reject, or human review.
- Consequences: obvious cases avoid an extra model call; uncertain revisions
  remain auditable; manual corrections rerun the Critic before downstream work.
