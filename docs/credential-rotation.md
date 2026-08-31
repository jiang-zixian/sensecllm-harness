# Provider credential rotation runbook

The repository no longer contains provider credentials. The account owner chose
on 2026-08-25 to continue using the existing ChatAnywhere inference credential
and SiliconFlow embedding/reranking credential. Rotation is therefore an
optional hardening action, not a release blocker; this runbook remains available
if that risk decision changes.

## Safe sequence

1. In each provider's account dashboard, create a replacement API key without
   revoking the currently working key yet.
2. Store the replacements only in the local secret manager or untracked `.env`:

   ```bash
   CHATANYWHERE_API_KEY=...
   SILICONFLOW_API_KEY=...
   ```

3. Open a fresh terminal so no previously exported value is reused, then verify the
   replacement keys independently:

   ```bash
   python -m sensor_rag check-api
   sensecllm analyze examples/demo_sensor.md --model deepseek-v3.2
   ```

4. Confirm the new run reaches `completed`, `usage.jsonl` records real calls,
   the report is non-empty, and RAG returns cited sources.
5. Revoke the old keys in both provider dashboards.
6. Repeat the short API probes. A revoked old key should fail authentication;
   the replacement key should still succeed.
7. Remove the old values from shell profiles, IDE run configurations, local
   history, CI variables, cloud secret stores, and any private copies of the old
   source. Do not paste either value into an issue, commit, screenshot, or chat.

## Repository verification

Run the committed scanner after rotation:

```bash
python scripts/check_secrets.py
git status --short
```

The first command must report no embedded provider credentials, and the second
must not show `.env` or another credential file. The scanner also checks stale
Python bytecode for literal bearer credentials. It intentionally excludes
`runs/`; if run artifacts have ever been shared externally, audit or delete
those copies separately even though the Harness does not log API keys.

## Rollback

If a replacement key fails before revocation, restore the previous environment
variable temporarily, diagnose provider permissions/quota/model access, and do
not revoke the old key until the replacement passes. After an old key is
revoked, rollback means creating another new key—not reintroducing the exposed
credential.
