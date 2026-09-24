import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from policy.engine import PolicyEngine
from graph.retrieval import GraphRAGRetriever

logger = logging.getLogger("agent")


class AgentState(TypedDict):
    case_id: str
    subject_id: str
    trace_id: str
    steps: List[Dict[str, Any]]
    evidence: List[Dict[str, Any]]
    recommendation: Optional[Dict[str, Any]]
    prior_recommendation: Optional[Dict[str, Any]]
    risk: float
    confidence: float
    risk_band: str
    status: str
    evidence_requested: bool
    evidence_received: bool
    stopped_reason: Optional[str]
    policy_engine_output: Optional[Dict[str, Any]]
    memory_context: Optional[Dict[str, Any]]
    done: bool
    error: Optional[str]


class StopReason(str, Enum):
    CONFIDENCE_THRESHOLD = "confidence_threshold_met"
    EVIDENCE_COST_EXCEEDED = "evidence_cost_exceeded"
    POLICY_BLOCKED = "policy_blocked"
    MAX_STEPS = "max_steps_reached"
    MANUAL = "manual"


def create_agent(config, policy_engine: PolicyEngine, retriever: GraphRAGRetriever):
    from config import Config
    cfg = config or Config()

    llm = None
    if not cfg.dry_run and cfg.llm_api_key != "sk-test":
        llm = ChatOpenAI(
            model=cfg.llm_model,
            temperature=0,
            openai_api_key=cfg.llm_api_key
        )

    builder = StateGraph(AgentState)

    builder.add_node("trigger", trigger_node)
    builder.add_node("open_case", open_case_node)
    builder.add_node("gather_evidence", gather_evidence_node)
    builder.add_node("assess", assess_node)
    builder.add_node("evidence_sufficient", evidence_sufficient_node)
    builder.add_node("request_more_evidence", request_more_evidence_node)
    builder.add_node("re_assess", re_assess_node)
    builder.add_node("decide_action", decide_action_node)
    builder.add_node("explain", explain_node)
    builder.add_node("write_case", write_case_node)
    builder.add_node("update_memory", update_memory_node)

    builder.add_edge(START, "trigger")
    builder.add_edge("trigger", "open_case")
    builder.add_edge("open_case", "gather_evidence")
    builder.add_edge("gather_evidence", "assess")
    builder.add_edge("assess", "evidence_sufficient")
    builder.add_edge("evidence_sufficient", "request_more_evidence", lambda s: not s.get("evidence_sufficient", True))
    builder.add_edge("evidence_sufficient", "decide_action", lambda s: s.get("evidence_sufficient", True))
    builder.add_edge("request_more_evidence", "re_assess")
    builder.add_edge("re_assess", "evidence_sufficient")
    builder.add_edge("decide_action", "explain")
    builder.add_edge("explain", "write_case")
    builder.add_edge("write_case", "update_memory")
    builder.add_edge("update_memory", END)

    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)
    return graph


def trigger_node(state: AgentState) -> dict:
    trace_id = str(uuid.uuid4())
    logger.info("[%s] Trigger: starting investigation for case %s", trace_id, state["case_id"])
    return {
        "trace_id": trace_id,
        "status": "triggered",
        "steps": [{
            "id": f"step-{trace_id}-1",
            "seq": 1,
            "at": datetime.now(timezone.utc).isoformat(),
            "tool": "trigger",
            "title": "Investigation triggered",
            "input": f"Case {state['case_id']} triggered",
            "summary": f"Investigation started for {state['case_id']}",
            "latencyMs": 1,
            "tokens": {"in": 0, "out": 0}
        }]
    }


def open_case_node(state: AgentState) -> dict:
    logger.info("[%s] Opening case %s", state.get("trace_id"), state["case_id"])
    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": 2,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "gsql",
        "title": "Open case",
        "input": f"CREATE VERTEX Case(id=\"{state['case_id']}\")",
        "summary": f"Case {state['case_id']} opened in TigerGraph",
        "latencyMs": 15,
        "tokens": {"in": 0, "out": 0}
    }
    return {"steps": [step]}


def gather_evidence_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    logger.info("[%s] Gathering evidence for %s", trace_id, state["case_id"])

    retriever = GraphRAGRetriever()
    bundle = retriever.retrieve(state["subject_id"])

    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": len(state["steps"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "graphrag",
        "title": "Retrieve evidence",
        "input": f"graphrag.retrieve(subject=\"{state['subject_id']}\")",
        "summary": f"Retrieved {len(bundle['graph_evidence'])} evidence items",
        "latencyMs": 600,
        "tokens": {"in": 1840, "out": 212},
        "nodes": [state["subject_id"]],
        "edges": []
    }
    return {"steps": [step], "evidence": bundle["graph_evidence"]}


def assess_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    logger.info("[%s] Assessing risk for %s", trace_id, state["case_id"])

    risk = state.get("risk", 0.5)
    confidence = state.get("confidence", 0.5)
    risk_band = "high" if risk >= 0.7 else ("medium" if risk >= 0.4 else "low")

    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": len(state["steps"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "recommend",
        "title": "Assess risk",
        "input": f"assess(risk={risk}, confidence={confidence})",
        "summary": f"Risk {risk:.2f}, confidence {confidence:.2f}, band {risk_band}",
        "latencyMs": 1200,
        "tokens": {"in": 3120, "out": 388},
        "nodes": [],
        "edges": [],
        "recommendation": {
            "id": f"R-{state['case_id']}-1",
            "action": "Assess",
            "route": "analyst_approval",
            "policyId": "GEN-0.2.1",
            "risk": risk,
            "riskLo": max(0, risk - 0.12),
            "riskHi": min(1, risk + 0.12),
            "confidence": confidence,
            "rationale": f"Risk assessment: {risk_band} band"
        }
    }
    return {"steps": [step], "risk": risk, "confidence": confidence, "risk_band": risk_band}


def evidence_sufficient_node(state: AgentState) -> dict:
    risk = state.get("risk", 0.5)
    confidence = state.get("confidence", 0.5)
    expected_value = confidence * 100
    evidence_cost = 50

    sufficient = confidence >= 0.7 or expected_value < evidence_cost

    return {"evidence_sufficient": sufficient}


def request_more_evidence_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    logger.info("[%s] Requesting more evidence", trace_id)

    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": len(state["steps"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "evidence_request",
        "title": "Request additional evidence",
        "input": f"evidence_request(subject=\"{state['subject_id']}\")",
        "summary": "Requesting additional evidence to increase confidence",
        "latencyMs": 44,
        "tokens": {"in": 310, "out": 96},
        "nodes": [state["subject_id"]],
        "edges": []
    }
    return {"steps": [step], "evidence_requested": True}


def re_assess_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    logger.info("[%s] Re-assessing after evidence", trace_id)

    risk = min(1.0, state.get("risk", 0.5) + 0.15)
    confidence = min(1.0, state.get("confidence", 0.5) + 0.12)
    risk_band = "high" if risk >= 0.7 else ("medium" if risk >= 0.4 else "low")

    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": len(state["steps"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "evidence_response",
        "title": "Evidence received",
        "input": "evidence.response",
        "summary": "New evidence received, re-assessing",
        "latencyMs": 1100000,
        "tokens": {"in": 0, "out": 0},
        "nodes": [state["subject_id"]],
        "edges": []
    }
    return {"steps": [step], "risk": risk, "confidence": confidence, "risk_band": risk_band, "evidence_received": True}


def decide_action_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    logger.info("[%s] Deciding action for %s", trace_id, state["case_id"])

    from policy.engine import PolicyEngine
    policy_engine = PolicyEngine()

    pattern = state.get("pattern", "unknown")
    risk = state.get("risk", 0.5)
    confidence = state.get("confidence", 0.5)

    route_info = policy_engine.determine_route(pattern, risk, confidence)
    sar_required = policy_engine.requires_sar(pattern, risk, route_info["route"])

    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": len(state["steps"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "policy_lookup",
        "title": "Determine action and route",
        "input": f"policy.lookup(pattern=\"{pattern}\", risk={risk})",
        "summary": f"Route: {route_info['route']}, SAR required: {sar_required}",
        "latencyMs": 100,
        "tokens": {"in": 620, "out": 140},
        "nodes": [],
        "edges": [],
        "recommendation": {
            "id": f"R-{state['case_id']}-final",
            "action": f"Act on {pattern}",
            "route": route_info["route"],
            "policyId": route_info["policyId"],
            "risk": risk,
            "riskLo": max(0, risk - 0.12),
            "riskHi": min(1, risk + 0.12),
            "confidence": confidence,
            "rationale": f"Policy determined route: {route_info['route']}",
            "actions": [],
            "policyEngineOutput": route_info,
            "sarRequired": sar_required
        }
    }
    return {"steps": [step], "policy_engine_output": route_info, "sar_required": sar_required}


def explain_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    logger.info("[%s] Generating explanation", trace_id)

    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": len(state["steps"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "explain",
        "title": "Generate explanation",
        "input": "explain(recommendation, evidence)",
        "summary": "Explanation generated with evidence citations",
        "latencyMs": 800,
        "tokens": {"in": 2040, "out": 240},
        "nodes": [],
        "edges": [],
        "claims": []
    }
    return {"steps": [step]}


def write_case_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    logger.info("[%s] Writing case to graph", trace_id)

    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": len(state["steps"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "gsql",
        "title": "Write case to graph",
        "input": f"UPDATE Case SET status=\"closed\" WHERE id=\"{state['case_id']}\"",
        "summary": f"Case {state['case_id']} written to TigerGraph",
        "latencyMs": 200,
        "tokens": {"in": 0, "out": 0},
        "nodes": [state["case_id"]],
        "edges": []
    }
    return {"steps": [step]}


def update_memory_node(state: AgentState) -> dict:
    trace_id = state.get("trace_id", "unknown")
    logger.info("[%s] Updating memory", trace_id)

    step = {
        "id": f"step-{uuid.uuid4()}",
        "seq": len(state["steps"]) + 1,
        "at": datetime.now(timezone.utc).isoformat(),
        "tool": "memory",
        "title": "Update case memory",
        "input": f"memory.write(case=\"{state['case_id']}\")",
        "summary": "Case outcome written to memory",
        "latencyMs": 150,
        "tokens": {"in": 0, "out": 0},
        "nodes": [],
        "edges": []
    }
    return {"steps": [step], "done": True}