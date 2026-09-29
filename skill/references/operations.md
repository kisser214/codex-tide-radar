# Operations notes

## Local

The service is dependency-free beyond Python 3.12. Set `PORT`, `POLL_SECONDS`, and `DATA_DIR` through the environment. The poller enforces a minimum interval of 120 seconds and persists state atomically under `DATA_DIR`.

## Docker

`compose.yaml` mounts `app.py` and `static/` read-only into the container and keeps `data/` on a separate persistent volume. After source updates, recreate the service and wait for the health check before reading `/api/status`.

## Verification checklist

1. `GET /healthz` returns `ok`.
2. `GET /api/status` returns `service: ok` or an explicitly documented degraded state.
3. `last_success_at`, source timestamps, and stale flags are coherent.
4. Model rows preserve upstream numeric values and display GPT generations in the intended order.
5. No upload or deployment step touches the remote `data` directory.

## Public release checklist

- Exclude `data/`, local logs, screenshots, FNOS exports, and browser captures.
- Scan tracked text for LAN IPs, tokens, cookies, Webhooks, and passwords.
- Document public sources and the no-login/no-model boundary.
- Do not claim real-time or official status when an upstream source is stale.
