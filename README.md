# commander-console

A free, open-source Docker-based connector for the **Verifone Commander** point-of-sale system, focused on fuel pricing management. Built to run on the same Docker host as other fuel-station tools (e.g. `tls-decoded`).

## What it does

- Reads current fuel prices from the Commander (cash / credit per grade)
- Writes price updates to the Commander database
- Pushes price changes to physical fuel dispensers (two-step process — DB update then dispenser push)
- Keeps a local history log of every price change (SQLite)
- Exposes a clean REST API for integrations
- Ships with a React dashboard for manual price management
- Includes a **mock mode** for development/testing without real hardware

## Architecture

```
frontend  (React + Vite)     → port 5010
connector (FastAPI + Python) → port 8100
Commander (Verifone POS)     → HTTPS port 443 on local network
```

## Quick start

### 1. Configure

```bash
cp .env.example .env
# Edit .env — set COMMANDER_PASSWORD to your service account password
```

Edit `config/commander.yaml`:
- Set `commander.host` to your Commander's IP address
- Set `commander.username` to your service account name (Manager + Helpdesk roles)
- For development without hardware, set `mock.enabled: true`

### 2. Run

```bash
docker compose up -d
```

- Dashboard: http://localhost:5010
- API: http://localhost:8100/api
- API docs: http://localhost:8100/docs

## Commander setup (real hardware)

1. Create a dedicated service user on the Commander with **Manager** and **Helpdesk** roles.
   - Do **not** use the `admin` account — newer firmware may require OTP/MFA for admin.
2. Note the Commander's IP address (check the unit's network settings).
3. Port-forward TCP 443 from your router to the Commander if accessing remotely.
4. Update `config/commander.yaml` with the IP and credentials.

## API reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | Connection health, last sync, mock mode flag |
| GET | `/api/prices` | All grades with current prices (cached) |
| GET | `/api/prices/live` | Force-fetch prices from Commander, bypass cache |
| POST | `/api/prices` | Update prices in Commander DB |
| POST | `/api/prices/push` | Push pending changes to dispensers |
| POST | `/api/prices/update-and-push` | Update DB then immediately push (atomic) |
| GET | `/api/prices/history` | Price change log |

Full interactive docs at `/docs` when the connector is running.

## Price update flow

```
User edits price in dashboard
        ↓
POST /api/prices  →  Commander: ufuelprices  (writes to Commander DB)
        ↓
POST /api/prices/push  →  Commander: cfuelprices  (pushes to dispensers)
```

The two-step process is intentional and matches the Commander's own workflow.
The dashboard requires explicit confirmation before pushing to dispensers.

## Mock mode

Set `mock.enabled: true` in `config/commander.yaml` to run without real hardware.
The mock driver returns NAXML-formatted fake prices, accepts updates in memory,
and simulates realistic network delays.

## Ports

| Service | Port |
|---------|------|
| Frontend | 5010 |
| Connector API | 8100 |

These ports were chosen to avoid conflicts with `tls-decoded` (which uses 8000 / 5005).

## Development

```bash
# Connector only (no Docker)
cd connector
pip install -r requirements.txt
uvicorn main:app --reload --port 8100

# Frontend only
cd frontend
npm install
npm run dev
```

## License

MIT — free to use, modify, and distribute.
