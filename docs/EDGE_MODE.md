# NexaFlow edge cache

NexaFlow can keep a read-only copy of the latest source-backed memory and
release decision at a warehouse or field node. This is useful when a site has
intermittent connectivity, but it is intentionally narrower than the central
console:

- no local Qwen inference is claimed;
- no Slack, GitHub, OSS, or deployment credentials are stored at the edge;
- no external action can be executed from the edge service;
- every response carries `human_approval_required: true` and
  `external_action_permitted: false`;
- the cache is marked `stale` or `unavailable` when central sync fails.

Run it locally:

```powershell
$env:CENTRAL_BASE_URL = "http://localhost"
docker compose -f docker-compose.edge.yml --profile edge up --build -d
Invoke-RestMethod http://localhost:8100/health
Invoke-RestMethod http://localhost:8100/memory
```

The central API remains authoritative. This is a bounded edge-readiness proof,
not a claim of on-device Qwen inference or autonomous field execution.
