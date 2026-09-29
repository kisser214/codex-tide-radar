---
name: codex-tide-radar
description: Maintain, test, and deploy the read-only Codex Tide Radar dashboard built from public reset, model-efficiency, Fast-history, and quota data; use when inspecting, changing, validating, or publishing this radar project.
metadata:
  short-description: Maintain and deploy Codex Tide Radar
---

# Codex Tide Radar

Use this skill for work on the Codex 潮汐雷达 project: a small Chinese dashboard that polls public Codex-related data and serves a read-only status page.

## Preserve the product boundary

- Keep the dashboard read-only and avoid login, Cookie, X-account access, model calls, voting, task submission, or private APIs.
- Treat `data/state.json` as runtime state, never as source code. Do not commit, upload, or overwrite it when packaging or deploying.
- Keep credentials, Webhooks, LAN addresses, reverse-proxy secrets, and personal browser data outside the repository.
- Show source freshness and uncertainty. Do not present community measurements as official OpenAI commitments.
- Preserve the distinction between history-based probabilities, official signals, and completed reset facts.

## Work from the project source of truth

Read the repository `README.md` first, then inspect only the files relevant to the request:

- `app.py`: public endpoints, normalization, local semantic adjudication, state persistence, and HTTP server.
- `static/index.html`: rendering and visual hierarchy.
- `compose.yaml`: container/runtime contract.
- `tests/test_radar.py`: deterministic regression coverage.

The model matrix is a presentation concern: keep all upstream rows, sort GPT generations newest first, and keep effort order `low`, `medium`, `high`, `xhigh`, `max`, `ultra`. Never copy an older model score into a newer model row.

## Change workflow

1. Make the smallest change that answers the request; do not refactor unrelated modules.
2. Add or update a deterministic test for changed normalization or semantic rules.
3. Run:

   ```powershell
   python -m unittest discover -s tests -v
   python -m py_compile app.py
   ```

4. For frontend changes, check that the page still contains the dynamic sections and that no runtime data file was added.
5. Before deployment, inspect the diff and scan for credentials, private addresses, and accidental `data/` files.

## Deployment workflow

Use the operator's explicitly supplied host and existing deployment path. Do not invent a host or upload target.

- Preserve the remote `data` directory.
- Replace only the requested source files (`app.py`, `static/`, or `compose.yaml`).
- Restart or recreate the project container after backend changes.
- Verify `/healthz`, `/api/status`, service freshness, and the requested visible behavior after restart.
- If a public GitHub push is requested, sanitize the package first and show the exact repository URL afterward.

Detailed endpoint and deployment notes are in [references/public-endpoints.md](references/public-endpoints.md) and [references/operations.md](references/operations.md). Read them only when the request needs that detail.
