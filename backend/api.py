"""FastAPI surface for the console. Contract matches frontend/src/api/client.ts.

Run: uvicorn api:app --port 8000   (after `python agent.py` has produced runs/)
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import agent
from data import store
from policy import AUTO

app = FastAPI(title="HHG fraud investigation agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
RUNS = agent.OUT_RUNS


def _run(case_id: str) -> dict:
    p = RUNS / f"{case_id}.json"
    if not p.exists():
        raise HTTPException(404, f"No investigation for {case_id}. Run `python agent.py {case_id}`.")
    return json.loads(p.read_text())


@app.get("/cases")
def cases():
    return json.loads((RUNS / "queue.json").read_text())


@app.get("/policies")
def policies():
    return agent.export_policies()


@app.get("/cases/{case_id}/investigation")
def investigation(case_id: str):
    return {k: v for k, v in _run(case_id).items() if k != "steps"}


@app.get("/cases/{case_id}/stream")
async def stream(case_id: str, pace_ms: int = 600):
    """Re-runs the agent live on this case, then streams its steps as SSE `step` events and a final `done`."""
    rows = store().case_pack
    row = rows[rows["case_id"] == case_id]
    if row.empty:
        raise HTTPException(404, f"Unknown case {case_id}")
    answer, run = await asyncio.to_thread(agent.investigate, row.iloc[0].to_dict())
    (agent.OUT_CASES / f"{case_id}.json").write_text(agent.dumps(answer, indent=2))
    (RUNS / f"{case_id}.json").write_text(agent.dumps(run))

    async def events():
        for step in run["steps"]:
            yield f"event: step\ndata: {agent.dumps(step)}\n\n"
            await asyncio.sleep(pace_ms / 1000 * (4 if step["tool"] == "evidence_response" else 1))
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


class ActionIn(BaseModel):
    actionId: str
    label: str


@app.post("/cases/{case_id}/actions")
def act(case_id: str, body: ActionIn):
    """Only auto-routed actions execute (policy §2). L1/L2 actions wait for a human approver."""
    final = {a["action"]: a for a in _run(case_id)["answer"]["next_best_actions"]["final"]}
    a = final.get(body.actionId)
    if not a:
        raise HTTPException(409, f"{body.actionId} is not in the current recommendation for {case_id}")
    if body.actionId not in AUTO:
        raise HTTPException(403, f"{body.actionId} needs {a['route']} approval under policy §2")
    return {"id": str(uuid.uuid4()), "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "caseId": case_id,
            "actionId": body.actionId, "label": body.label, "actor": "agent (auto route)", "status": "committed"}
