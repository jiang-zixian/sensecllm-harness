# SenSec graph V2

This directory is an isolated copy of `src/steps-graph`. The original directory
is unchanged.

V2 changes prompts only:

- Step 2 prefers one or two target-grounded mechanisms and permits no candidate
  when the local component, reachable modality, and physical operation are not
  all supported.
- Step 4 is restored unchanged from `src/steps-graph` (V1).

No verifier module is included in V2. Step 3 is invoked with
`use_verifier=False`, and attempting to enable it raises an error. Step 4 uses
the existing generator and deterministic schema/range validation, not a
verifier model.
