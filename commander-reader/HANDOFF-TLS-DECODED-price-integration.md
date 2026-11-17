# Handoff: Wire hourly fuel prices from commander-reader into TLS Decoded

> **For:** Claude (TLS Decoded session)
> **From:** Raffi, via the commander-reader build session
> **Status:** commander-reader is live and tested against the real Commander unit at this station.

## What you're integrating with

`commander-reader` is a read-only REST proxy already running on this station's Docker host:

```
http://<host>:8200/prices
```

It logs into the Commander over NAXML, polls prices every 60s, and caches them. No auth needed — it's LAN-only. Full endpoint list at `http://<host>:8200/docs`.

Confirmed working live: `GET /health`, `GET /prices`, `GET /prices/live`. Not yet verified: `GET /pumps` (skip it for now — unrelated to this task anyway).

## The one thing that matters most: grade IDs are per-station, not universal

**Every station's Commander configuration is different.** Grade names repeat, grade IDs don't map to the same physical product across stations, and unused/placeholder grade slots are mixed in with real ones. Do not build a "read all grades" or "match by name" integration that assumes consistency across stations — it will silently pull wrong prices somewhere.

**For this specific station**, live data currently looks like this (trimmed):

```json
{
  "grades": [
    {"id": 1, "name": "REGULAR",   "in_effect": {"cash": 5.579, "credit": 5.579}},
    {"id": 2, "name": "PLUS",      "in_effect": {"cash": 5.779, "credit": 5.779}},
    {"id": 3, "name": "SUPER",     "in_effect": {"cash": 5.879, "credit": 5.879}},
    {"id": 4, "name": "DIESEL#2",  "in_effect": {"cash": 4.479, "credit": 4.479}},
    {"id": 7, "name": "DIESEL#2",  "in_effect": {"cash": 6.679, "credit": 6.679}}
  ]
}
```

Note **id 4 and id 7 are both named `DIESEL#2`** — same name, different grades. Only one of them is the diesel actually sold at this station's pumps.

### This station's confirmed mapping

| TLS product | Commander grade id | Commander name | Notes |
|---|---|---|---|
| Unleaded | **1** | REGULAR | |
| Super | **3** | SUPER | |
| Diesel | **7** | DIESEL#2 | **Not id 4** — id 4 is also named DIESEL#2 but is not what this station sells. Confirmed by the station operator, not guessed from the API. |

**Ignore everything else returned by `/prices` at this station**, including `PLUS` (id 2, not sold here) and any other grade ids present in the response (there are placeholder/unused slots too, e.g. `UNUSED1`...`UNUSEDn`). Don't sync grades just because they appear in the JSON.

### What this means for the integration

- Build the price sync around an explicit **per-station grade-id allowlist**, not "sync all grades" or "sync anything matching this name string." Something like a config map: `{station_id: {tls_product_key: commander_grade_id}}`.
- Before wiring up any station beyond this one, **ask which grade ids are actually sold there** — pull `GET /prices`, show the raw list, and get it confirmed by whoever knows the station (don't assume based on name or id pattern from this station).
- Grade *names* are not reliable keys (see the duplicate `DIESEL#2` above). Grade *ids* are, but only within a single station's config — they're not portable across stations either.

## Which price fields to use

Each grade has two tiers:

```json
"in_effect": { "cash": 5.579, "credit": 5.579 },   // what's live at the pump right now
"pending":   { "cash": 1.112, "credit": 1.122 }    // staged, not yet pushed — often garbage/test values
```

For "current price" purposes, use **`in_effect`**, not `pending`. `pending` values on this unit currently look like placeholder data (sequential 1.112/1.122, 2.112/2.122, etc. across grades) — don't surface those as real prices anywhere.

## Suggested integration shape

- Poll `GET /prices` (the cached endpoint, refreshes every 60s server-side) on your own hourly cadence — no need to hit `/prices/live` for a once-an-hour job, that's for on-demand force-refreshes.
- Response includes `stale: true` if the cache is older than the poll interval (e.g. commander-reader lost connection to the Commander) — treat a stale response as "skip this hour, don't overwrite good data with unknown data," not as a hard failure.
- `GET /health` returns `connected: false` (still HTTP 200) if the Commander itself is unreachable — check that before trusting a `/prices` response, or just treat any 502 / `stale: true` the same way: skip and retry next cycle.
- No retries/backoff needed on your end for transient failures — commander-reader's own poll loop already retries against the Commander every 60s and will self-heal.

## Open questions to resolve before going live

1. Confirm the grade-id mapping above with whoever set up this station's Commander (id 1 / 3 / 7) — I inferred it from what Raffi told me, not from the API alone, since the API has no way to know which configured grade is the one physically wired to a live pump.
2. Decide what TLS should do when a grade is temporarily missing from the poll (e.g. Commander down) — carry forward last-known price, or flag as unknown?
3. If/when you're adding a second station, do not reuse this station's `{1, 3, 7}` mapping — pull fresh and confirm per station.
