# Agentic Fraud Investigation Backend

Backend system for agentic fraud investigation on TigerGraph Savanna.

## Prerequisites

- Python 3.11+
- TigerGraph Savanna instance (cloud)
- OpenAI API key

## Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your Savanna credentials and LLM key
```

## TigerGraph Savanna Connection

Set in `.env`:
- `SAVANNA_HOST` - Your Savanna instance URL
- `SAVANNA_USERNAME` - TigerGraph username
- `SAVANNA_PASSWORD` - TigerGraph password
- `SAVANNA_GRAPH` - Graph name (default: FraudGraph)
- `LLM_API_KEY` - OpenAI API key
- `DRY_RUN` - Set to `true` to run without database

## Schema Installation

```bash
# Install graph schema on TigerGraph
python -m graph.loader --install-schema schema.gsql
```

## Data Loading

```bash
# Load ~590k transactions, device/connection records, closed cases, policies, patterns
python -m graph.loader
```

The loader is idempotent and resumable. Progress is logged.

## Running Batch Investigation

```bash
# Generate all 20 answer files
python batch.py

# Output goes to /tmp/fraud_answers/
```

## Running the API Server

```bash
# Start FastAPI server
python -m api.main

# Server runs on http://localhost:8000
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_policy.py -v
pytest tests/test_stopping_rule.py -v
pytest tests/test_full_investigation.py -v
```

## Dry Run Mode

```bash
# Run everything without TigerGraph or LLM
DRY_RUN=true python batch.py
DRY_RUN=true python -m api.main
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /cases | List all cases |
| POST | /investigate/{case_id} | Start/resume investigation |
| GET | /cases/{case_id}/stream | SSE stream of agent steps |
| GET | /cases/{case_id} | Full case record |
| GET | /cases/{case_id}/graph | Evidence subgraph |
| POST | /cases/{case_id}/evidence | Inject evidence |
| POST | /cases/{case_id}/act | Execute action |
| GET | /cases/{case_id}/export | Export answer file |

## Architecture

1. **Graph Layer** (schema.gsql, loader.py): TigerGraph graph schema and bulk loader
2. **GraphRAG** (retrieval.py): Grounded evidence retrieval via vector search
3. **Policy Engine** (policy/engine.py): Deterministic policy authorization
4. **Agent** (agent/state_machine.py): LangGraph state machine for investigation
5. **Memory** (memory.py): Case persistence and similar case retrieval
6. **API** (api/main.py): FastAPI surface with SSE streaming

## Output Contract

Each answer file contains:
- Case record with investigation trail
- Evidence items with source references
- Findings, decisions, actions
- Recommendation with risk assessment
- Approval route recorded before and after evidence
- SAR (where policy requires it)
- Next best action with approval route recorded twice

## Evaluation Criteria

- Investigation accuracy (25%)
- Next best action under uncertainty (25%)
- Agentic design (15%)
- Innovation (15%)
- Case summary + explainability (10%)
- Demo (10%)
