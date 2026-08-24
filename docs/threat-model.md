# Threat model

## Assets and trust boundaries

Assets are provider credentials, uploaded documents, unpublished device facts,
run artifacts, episodic cases, and model/RAG provenance. Trust boundaries exist
at the upload API, model gateways, RAG service, legacy subprocess, SQLite store,
and artifact download endpoint.

## Main threats and controls

| Threat | Control | Residual risk |
|---|---|---|
| Credential disclosure | environment-only secrets, redacted HTTP failures, secret scan | keys formerly shared must be rotated manually |
| Path traversal / arbitrary artifact read | hex run IDs, allowlisted upload extensions, resolved-path containment | local operators still control the host |
| Oversized or malicious upload | 15 MiB limit, isolated parsing subprocess, timeout | PDF parser vulnerabilities require dependency updates/sandboxing |
| Prompt injection in papers/device docs | artifacts treated as data; evidence-only RAG prompt; deterministic checks | models can still follow adversarial content |
| Cross-run contamination | run-scoped paths and fresh legacy subprocesses | shared provider/RAG quotas remain global |
| Historical-case leakage | episodic results labelled priors and kept outside target evidence | poor prompts may over-weight priors |
| Unsupported security claims | accepted-path linkage, Critic, citations, human gate | evaluation depends on expert labels |
| Denial of service / cost exhaustion | time, attempt, token accounting, cancellation, file limit | hard token rejection requires provider streaming/token hooks |

The API is intended for a trusted local demo. Internet exposure additionally
requires authentication, TLS, per-user authorization, rate limits, malware
scanning, and a hardened container profile.
