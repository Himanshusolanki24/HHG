# HHG: agentic fraud investigation

An AI agent investigates fraud cases on a TigerGraph fraud graph, and an analyst console shows its evidence, uncertainty and recommendations.

| Folder | What it is | Details |
|---|---|---|
| [`frontend/`](frontend/README.md) | Analyst console: case queue, graph, timeline, agent trace, decision panel. React, TypeScript, Vite. | Run instructions, API contract, 90-second demo script |
| [`backend/`](backend/README.md) | Investigation agent: LangGraph state machine, GraphRAG, policy engine, FastAPI with SSE. Python 3.11+. | Setup, schema install, data loading, batch run, tests |

## Quick start

Console only, on fixture data (no backend needed):

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Backend in dry-run mode (no TigerGraph or LLM):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
DRY_RUN=true python -m api.main     # http://localhost:8000
```

For a live run, put Savanna and OpenAI credentials in `backend/.env`. The variable names are listed in `backend/README.md`. `.env` is gitignored, so never commit it.

## Connecting the two

Point the console at the backend with:

```bash
cd frontend
VITE_API_URL=http://localhost:8000 npm run dev
```

**The two APIs do not match yet.** The console expects the routes in `frontend/README.md`, but the backend currently exposes a different set:

| Console expects | Backend has |
|---|---|
| `GET /cases` | `GET /cases` |
| `GET /cases/{id}/stream` (SSE, `step` / `done` events) | `GET /cases/{id}/stream` |
| `GET /cases/{id}/investigation` | `GET /cases/{id}` and `GET /cases/{id}/graph` |
| `GET /policies` | none |
| `POST /cases/{id}/actions` | `POST /cases/{id}/act` |

Close the gap on one side before a live demo: add the routes to FastAPI, or adapt `httpApi` in `frontend/src/api/client.ts`. Until then, the console's fixture mode is the reliable demo path.
