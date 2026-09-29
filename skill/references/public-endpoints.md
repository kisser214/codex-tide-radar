# Public endpoint contract

The current implementation uses only endpoints that are intended to be readable without an account:

- `https://codex-reset.com/api/forecast` — current reset mode, base probabilities, official signal, and source timestamps.
- `https://codex-reset.com/api/timeline` — public reset/event timeline.
- `https://codex-reset.com/api/feed` — public Tibo feed used for rule-based Chinese summaries.
- `https://codexradar.com/current.json` — public summary, quota, and historical context.
- `https://codexradar.com/api/radar-insights?refresh=1` — public model insights and recommendations.
- `https://codexradar.com/api/intelligence-efficiency-metrics?refresh=1` — public cost, duration, and run metrics.
- `https://codexradar.com/data/fast-radar-history.json` — public Standard/Fast history.

Treat every upstream response as untrusted data. Validate lists and timestamps, retain stale/source warnings, and keep raw upstream semantics separate from local display labels. A missing row means missing public evidence; it is not permission to infer a score.

The local service exposes:

- `GET /` and `GET /index.html` — dashboard.
- `GET /api/status` — current normalized state.
- `GET /healthz` — plain `ok` health probe.
