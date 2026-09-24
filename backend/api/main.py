import os
import sys
import json
import logging
import uuid
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from batch import build_answer_file
import asyncio

from config import Config, config as app_config
from models import CaseRecord, AnswerFile, AgentStep, Evidence, Recommendation, ApprovalRoute, SAR
from policy.engine import PolicyEngine
from graph.retrieval import GraphRAGRetriever
from graph.loader import TigerGraphLoader
from agent.state_machine import AgentState, create_agent
from memory import CaseMemory

logger = logging.getLogger("api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler()]
)

app = FastAPI(title="Agentic Fraud Investigation Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

policy_engine = PolicyEngine()
retriever = GraphRAGRetriever(config=app_config)
case_memory = CaseMemory(config=app_config)
loader = TigerGraphLoader(app_config)

_investigations: Dict[str, Dict[str, Any]] = {}
_answer_files: Dict[str, AnswerFile] = {}


def init_db():
    conn = sqlite3.connect(app_config.sqlite_log_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_log (
            id TEXT PRIMARY KEY,
            trace_id TEXT,
            query_type TEXT,
            query_text TEXT,
            latency_ms FLOAT,
            tokens_in INT,
            tokens_out INT,
            cost REAL,
            timestamp TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_log (
            id TEXT PRIMARY KEY,
            trace_id TEXT,
            model TEXT,
            prompt TEXT,
            response TEXT,
            latency_ms FLOAT,
            tokens_in INT,
            tokens_out INT,
            cost REAL,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


def log_query(trace_id: str, query_type: str, query_text: str, latency_ms: float, tokens_in: int, tokens_out: int, cost: float):
    conn = sqlite3.connect(app_config.sqlite_log_path)
    conn.execute("""
        INSERT INTO query_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), trace_id, query_type, query_text, latency_ms, tokens_in, tokens_out, cost, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()


def log_llm_call(trace_id: str, model: str, prompt: str, response: str, latency_ms: float, tokens_in: int, tokens_out: int, cost: float):
    conn = sqlite3.connect(app_config.sqlite_log_path)
    conn.execute("""
        INSERT INTO llm_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), trace_id, model, prompt, response, latency_ms, tokens_in, tokens_out, cost, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()


class InvestigateRequest(BaseModel):
    case_id: str


class EvidenceInjectRequest(BaseModel):
    evidence_id: str
    kind: str
    label: str
    summary: str
    source: str
    nodes: List[str] = []


class ActionExecuteRequest(BaseModel):
    action_id: str
    label: str


@app.get("/cases")
async def list_cases():
    from fixtures.cases import load_cases
    cases = []
    for c in load_cases():
        inv = _investigations.get(c["id"])
        status = c["status"]
        if inv and inv.get("done"):
            status = "ready_to_act" if inv.get("recommendation") else status
        cases.append({
            "id": c["id"],
            "title": c["title"],
            "trigger": c["trigger"],
            "pattern": c["pattern"],
            "status": status,
            "risk": c["risk"],
            "confidence": c["confidence"],
            "stateSince": c["stateSince"],
            "hasRun": c.get("hasRun", False)
        })
    return cases


@app.get("/policies")
async def list_policies():
    from fixtures.cases import load_policies
    return load_policies()


@app.get("/cases/{case_id}")
async def get_case(case_id: str):
    answer = _answer_files.get(case_id)
    if not answer:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return answer.model_dump()


@app.get("/cases/{case_id}/investigation")
async def get_investigation(case_id: str):
    inv = _investigations.get(case_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"No investigation for {case_id}")
    return {k: v for k, v in inv.items() if k != "steps"}


@app.post("/investigate/{case_id}")
async def investigate(case_id: str):
    from fixtures.cases import load_cases, load_investigation
    from models import CaseRecord, AnswerFile, RiskAssessment

    cases_data = load_cases()
    case = next((c for c in cases_data if c["id"] == case_id), None)
    if not case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    investigation = load_investigation(case_id)
    answer = build_answer_file(case, investigation)
    _answer_files[case_id] = answer

    trace_id = str(uuid.uuid4())
    steps = []

    step1 = AgentStep(
        id=f"s1-{trace_id}", seq=1, at=datetime.now(timezone.utc),
        tool="gsql", title="Open case", input=f"Case {case_id}",
        summary=f"Investigation started for {case_id}",
        latencyMs=1, tokens={"in": 0, "out": 0},
        nodes=[case.get("subjectId", case_id)]
    )
    steps.append(step1.model_dump())

    if investigation and investigation.get("steps"):
        for inv_step in investigation["steps"]:
            steps.append(inv_step)

    _investigations[case_id] = {
        "caseId": case_id,
        "subjectId": case.get("subjectId", case_id),
        "alertAt": case["stateSince"],
        "steps": steps,
        "done": True,
        "trace_id": trace_id,
        "recommendation": answer.recommendation.model_dump(),
        "risk": case["risk"],
        "confidence": case["confidence"]
    }

    return {"case_id": case_id, "trace_id": trace_id, "status": "complete"}


@app.get("/cases/{case_id}/stream")
async def stream_steps(case_id: str):
    inv = _investigations.get(case_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"No investigation for {case_id}")

    steps = inv.get("steps", [])

    async def event_generator():
        for step in steps:
            if isinstance(step, dict):
                step_data = step
            else:
                step_data = step.model_dump() if hasattr(step, "model_dump") else step
            step_data = {k: v.isoformat() if hasattr(v, 'isoformat') else v for k, v in step_data.items()}
            yield f"data: {json.dumps(step_data)}\n\n"
            await asyncio.sleep(0.1)
        yield "data: {\"event\":\"done\"}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/cases/{case_id}/evidence")
async def inject_evidence(case_id: str, req: EvidenceInjectRequest):
    inv = _investigations.get(case_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"No investigation for {case_id}")

    new_evidence = {
        "id": req.evidence_id,
        "kind": req.kind,
        "label": req.label,
        "summary": req.summary,
        "source": req.source,
        "nodes": req.nodes
    }

    if "evidence" not in inv:
        inv["evidence"] = []
    inv["evidence"].append(new_evidence)

    re_assessment = {
        "id": f"re-{case_id}",
        "action": "Re-assessed after evidence",
        "route": "dual_approval",
        "policyId": "AML-4.2.2",
        "risk": min(1.0, inv.get("risk", 0.5) + 0.15),
        "riskLo": 0, "riskHi": 0,
        "confidence": min(1.0, inv.get("confidence", 0.5) + 0.12),
        "rationale": "Re-assessed after new evidence",
        "causedBy": [req.evidence_id]
    }
    inv["re_assessed_recommendation"] = re_assessment

    return {"case_id": case_id, "evidence_id": req.evidence_id, "re_assessed": re_assessment}


@app.post("/cases/{case_id}/act")
async def execute_action(case_id: str, req: ActionExecuteRequest):
    inv = _investigations.get(case_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"No investigation for {case_id}")

    rec = inv.get("recommendation") or inv.get("re_assessed_recommendation")
    action_allowed = False
    policy_id = ""

    if rec:
        for action in rec.get("actions", []):
            if action.get("id") == req.action_id:
                action_allowed = action.get("allowed", False)
                policy_id = action.get("policyId", "")
                break

    if not action_allowed:
        return {
            "case_id": case_id,
            "action_id": req.action_id,
            "status": "rejected",
            "reason": f"Action {req.action_id} not permitted by policy {policy_id}"
        }

    audit = {
        "id": str(uuid.uuid4()),
        "at": datetime.now(timezone.utc).isoformat(),
        "caseId": case_id,
        "actionId": req.action_id,
        "label": req.label,
        "actor": "system.agent",
        "status": "committed"
    }

    return audit


@app.get("/cases/{case_id}/export")
async def export_answer(case_id: str):
    answer = _answer_files.get(case_id)
    if not answer:
        raise HTTPException(status_code=404, detail=f"No answer file for {case_id}")
    return answer.model_dump()


@app.get("/cases/{case_id}/graph")
async def get_graph(case_id: str):
    from fixtures.cases import load_investigation
    inv = load_investigation(case_id)
    if not inv:
        raise HTTPException(status_code=404, detail=f"No graph data for {case_id}")
    return inv


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app.router.lifespan = lifespan

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)