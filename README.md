# HHG: agentic fraud investigation on TigerGraph

An agent investigates card-fraud alerts on the IEEE-CIS dataset (TigerGraph × Hacker House Goa). It decides under the bank's policy,
asks for evidence when uncertain, shows how its recommendation changed, and writes each case back to the graph. An analyst console shows the whole run.

| Folder | What |
|---|---|
| [`cases/`](cases) | **The submission**: 20 answer files in the README format, validated by `backend/validate.py` |
| [`backend/`](backend/README.md) | The agent: graph evidence, case memory, calibrated scoring, policy engine, Mistral writing, TigerGraph store, FastAPI + SSE |
| [`frontend/`](frontend/README.md) | The console: case queue, graph, timeline, streaming agent trace, answer file, decision panel with before/after |

## Quick start

```bash
# 1. agent (needs the dataset folder; set DATA_DIR in backend/.env)
cd backend && python3.14 -m venv .venv && .venv/bin/pip install -e . && cp .env.example .env
.venv/bin/python calibrate.py && .venv/bin/python agent.py && .venv/bin/python validate.py

# 2. console on the agent's output (no server needed)
cd ../frontend && npm install && npm run sync && npm run dev      # http://localhost:5173

# 3. or live: the console streams a fresh agent run for each case
cd ../backend && .venv/bin/uvicorn api:app --port 8000
cd ../frontend && VITE_API_URL=http://localhost:8000 npm run dev
```

`backend/.env` holds the Savanna and Mistral credentials. It is gitignored; `backend/.env.example` lists the keys.
