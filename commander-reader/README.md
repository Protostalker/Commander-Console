# commander-reader

A Dockerized, **read-only** REST API proxy for the Verifone Commander POS
system. It handles NAXML auth, session tokens, and self-signed certs
internally and exposes clean JSON endpoints so other tools (TLS Decoded,
dashboards, Grafana, scripts) can get Commander data without ever touching
the Commander protocol directly.

Forked from `commander-console` (the read+write connector with a React
dashboard). This project shares no code path with anything that writes to
Commander — see "Read-only guarantee" below.

## Architecture

```
Verifone Commander POS
        |  NAXML over HTTPS (self-signed cert, session tokens, XML)
        v
commander-reader :8200   <- this project
  Docker container, Python 3.12 / FastAPI
  Background polling every 60s (configurable)
  In-memory cache + SQLite change log
        |  Plain HTTP, clean JSON, no auth needed
        v
TLS Decoded / Dashboards / Grafana / scripts / anything
```

## Quick start

```bash
cd commander-reader
cp .env.example .env
# edit .env: set COMMANDER_HOST and COMMANDER_PASSWORD

docker compose up -d

curl http://localhost:8200/health
curl http://localhost:8200/prices
curl "http://localhost:8200/totals?period=day"
```

Swagger UI: `http://localhost:8200/docs`

Runs on port **8200** — chosen to avoid conflicts with `commander-console`
(8100/5010) and `tls-decoded` (8000/5005) if all three run on the same
Docker host.

## Commander service account

Use a dedicated account with **Manager** + **Helpdesk** roles, not `admin`
(newer firmware may require OTP/MFA for admin). This account only needs
read access — it never calls a write command.

## Read-only guarantee

`app/commander_client.py` implements exactly four Commander commands:
`validate` (login), `vfuelprices`, `vfueltotals`, `vmaintfprht`, `vfuelcfg`.
The write commands `ufuelprices` and `cfuelprices` do not appear anywhere
in this codebase — not behind a flag, not commented out, not imported.
There is no `naxml_builder.py` equivalent here, and no POST/PUT/PATCH route
in any router.

```bash
grep -rn "ufuelprices\|cfuelprices" app/   # should return nothing
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Connection health, session age, last fetch age |
| GET | `/prices` | Cached fuel prices (in-effect + pending) |
| GET | `/prices/live` | Force-fetch prices, bypass cache |
| GET | `/prices/history` | Locally detected price-change log (`limit`, `offset`) |
| GET | `/totals?period=` | Sales totals: `shift`, `day`, `month`, or `year` |
| GET | `/pumps` | Per-pump/hose lifetime totals (see caveat below) |
| GET | `/config` | Site fuel config (raw XML — schema not yet parsed) |
| GET | `/metrics` | Prometheus exposition format |

Full interactive docs at `/docs`.

## Configuration

All via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `COMMANDER_HOST` | *(required)* | Hostname or IP of the Commander unit |
| `COMMANDER_PORT` | `443` | HTTPS port |
| `COMMANDER_USERNAME` | `MANAGER` | Commander account username |
| `COMMANDER_PASSWORD` | *(required)* | Commander account password |
| `COMMANDER_VERIFY_SSL` | `false` | Set `true` only if the cert is valid |
| `POLL_INTERVAL_SECONDS` | `60` | How often to refresh the price cache |
| `SESSION_REFRESH_MINUTES` | `25` | Proactive re-login before ~30 min token expiry |
| `PORT` | `8200` | Port to listen on inside the container |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `DB_PATH` | `/app/data/history.db` | SQLite path (set automatically in compose) |

## Known caveat: `GET /pumps` is unverified

`vmaintfprht` (lifetime pump/hose totals) was never called against a live
Commander unit while this project was built — only `vfuelprices` and
`vfueltotals` were confirmed on real hardware. `app/naxml_parser.py::parse_pump_totals()`
is a best-effort parser based on the field-naming patterns seen in
`vfueltotals` responses, not a confirmed schema.

It's defensive: if it doesn't recognize the response shape, `/pumps`
returns `502` with a clear message instead of returning wrong numbers, and
the raw XML is logged (`docker compose logs commander-reader`) for
debugging. Before relying on this endpoint:

1. `curl http://localhost:8200/pumps`
2. If it 502s, check the logs for the raw `vmaintfprht` XML
3. Adjust the candidate tag names in `parse_pump_totals()` to match

Every other endpoint (`/prices`, `/totals`, `/config`) is a direct port of
parsing logic already proven against the real unit.

## Graceful degradation

- Commander unreachable → `/health` returns `connected: false`, still HTTP 200
- `/prices` serves the last cached snapshot with `stale: true` if the cache
  has outlived the poll interval
- `/totals`, `/pumps`, `/config` return HTTP 502 with a clear error when
  Commander can't be reached (nothing cached for these — always live)
- The poll loop keeps retrying; things recover automatically when Commander
  comes back

## No authentication (by design, for now)

This service has no auth layer — it's meant for an internal LAN alongside
`commander-console` and `tls-decoded`. Anyone who can reach port 8200 can
read prices and totals. That's a much smaller exposure than a write-capable
API (which is the whole reason this project exists separately from
`commander-console`), but it's still worth restricting at the network
level (firewall / VLAN) rather than exposing the port to the open internet.
If that's not sufficient, add an API-key middleware before deploying beyond
a trusted LAN.

## Development (without Docker)

```bash
pip install -r requirements.txt
export COMMANDER_HOST=... COMMANDER_PASSWORD=...
uvicorn app.main:app --reload --port 8200
```

## License

MIT.
