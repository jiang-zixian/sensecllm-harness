# ADR 001: Isolate legacy stages in subprocesses

- Status: Accepted
- Context: the retained pipeline uses module-level configuration and was not
  designed for concurrent server requests.
- Decision: execute every domain stage in a fresh subprocess with run-scoped
  paths and environment, while the Harness owns supervision and checkpoints.
- Consequences: concurrent runs cannot overwrite each other's globals; stages
  are cancellable and time-bounded. Process startup and JSON artifacts add a
  small overhead, accepted in exchange for compatibility and fault isolation.
