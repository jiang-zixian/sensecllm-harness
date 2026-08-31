# ADR 001: Isolate domain stages in subprocesses

- Status: Accepted
- Context: domain stages use module-level runtime configuration and run-scoped
  artifacts, so concurrent server requests require an explicit isolation boundary.
- Decision: execute every domain stage in a fresh subprocess with run-scoped
  paths and environment, while the Harness owns supervision and checkpoints.
- Consequences: concurrent runs cannot overwrite each other's globals; stages
  are cancellable and time-bounded. Process startup and JSON artifacts add a
  small overhead, accepted in exchange for clear execution boundaries and fault
  isolation.
