from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Trigger(str, Enum):
    risk_score = "risk_score"
    customer_report = "customer_report"
    analyst_request = "analyst_request"


class Pattern(str, Enum):
    card_testing = "card_testing"
    account_takeover = "account_takeover"
    mule_network = "mule_network"
    app_scam = "app_scam"
    synthetic_identity = "synthetic_identity"
    friendly_fraud = "friendly_fraud"


class CaseStatus(str, Enum):
    open = "open"
    awaiting_evidence = "awaiting_evidence"
    ready_to_act = "ready_to_act"
    closed = "closed"


class Route(str, Enum):
    auto_execute = "auto_execute"
    analyst_approval = "analyst_approval"
    dual_approval = "dual_approval"


class EntityType(str, Enum):
    account = "account"
    card = "card"
    device = "device"
    email = "email"
    ip = "ip"
    transaction = "transaction"
    prior_case = "prior_case"


class Claim(BaseModel):
    text: str
    ref: Dict[str, str] = Field(..., description="{\"kind\": \"node|policy|evidence\", \"id\": \"...\"}")


class Unknown(BaseModel):
    id: str
    question: str
    resolvedBy: str
    infoGain: float = Field(..., ge=0, le=1)
    resolved: bool = False


class ActionOption(BaseModel):
    id: str
    label: str
    allowed: bool
    policyId: str
    reason: Optional[str] = None


class RiskAssessment(BaseModel):
    risk: float = Field(..., ge=0, le=1)
    riskLo: float = Field(..., ge=0, le=1)
    riskHi: float = Field(..., ge=0, le=1)
    confidence: float = Field(..., ge=0, le=1)
    band: str = "low"


class Recommendation(BaseModel):
    id: str
    action: str
    route: Route
    policyId: str
    risk: float = Field(..., ge=0, le=1)
    riskLo: float = Field(..., ge=0, le=1)
    riskHi: float = Field(..., ge=0, le=1)
    confidence: float = Field(..., ge=0, le=1)
    rationale: str = ""
    unknowns: List[Unknown] = Field(default_factory=list)
    actions: List[ActionOption] = Field(default_factory=list)
    causedBy: List[str] = Field(default_factory=list)


class ApprovalRoute(BaseModel):
    route: Route
    policyId: str
    required_approvers: int = Field(default=1)
    pre_evidence_route: Route = Field(..., description="Route before additional evidence was requested")
    post_evidence_route: Route = Field(..., description="Route after additional evidence was received")
    pre_risk: float = Field(..., description="Risk before evidence")
    post_risk: float = Field(..., description="Risk after evidence")
    pre_confidence: float = Field(..., description="Confidence before evidence")
    post_confidence: float = Field(..., description="Confidence after evidence")
    evidence_caused_change: bool = False
    changed_by: Optional[str] = None


class Evidence(BaseModel):
    id: str
    kind: str = Field(..., description="graph|policy|external|retrieval")
    label: str
    summary: str
    source: str
    nodes: List[str] = Field(default_factory=list)
    edges: List[str] = Field(default_factory=list)
    timestamp: Optional[datetime] = None


class AgentStep(BaseModel):
    id: str
    seq: int
    at: datetime
    tool: str
    title: str
    input: str
    summary: str
    latencyMs: float
    tokens: Dict[str, int] = Field(default_factory=lambda: {"in": 0, "out": 0})
    claims: List[Claim] = Field(default_factory=list)
    nodes: List[str] = Field(default_factory=list)
    edges: List[str] = Field(default_factory=list)
    evidence: Optional[Evidence] = None
    recommendation: Optional[Recommendation] = None
    delayMs: Optional[float] = None


class SAR(BaseModel):
    id: str
    case_id: str
    filed_at: datetime
    filing_officer: str
    mlro_delegate: Optional[str] = None
    status: str = "pending"
    reason: str = ""
    risk_score: float = Field(..., ge=0, le=1)
    policy_clause: str = ""
    evidence_summary: str = ""


class CaseRecord(BaseModel):
    id: str
    title: str
    trigger: Trigger
    pattern: Pattern
    status: CaseStatus
    risk: float = Field(..., ge=0, le=1)
    confidence: float = Field(..., ge=0, le=1)
    stateSince: datetime
    hasRun: bool = False
    subjectId: Optional[str] = None
    investigation_trail: List[AgentStep] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    findings: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    recommendation: Optional[Recommendation] = None
    approval_route: Optional[ApprovalRoute] = None
    sar: Optional[SAR] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AnswerFile(BaseModel):
    case: CaseRecord
    evidence: List[Evidence]
    findings: List[str]
    decisions: List[str]
    actions: List[str]
    recommendation: Recommendation
    approval_route: ApprovalRoute
    sar: Optional[SAR] = None
    risk_assessment: RiskAssessment
    generated_at: datetime


class GraphNode(BaseModel):
    id: str
    type: EntityType
    label: str
    risk: float = Field(..., ge=0, le=1)
    attrs: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    rel: str
    weight: float = 1.0


class Transaction(BaseModel):
    id: str
    at: datetime
    amount: float
    merchant: str
    direction: str
    flagged: bool


class SimilarCase(BaseModel):
    caseId: str
    similarity: float
    outcome: str
    decision: str
    analystNote: str


class InvestigationMeta(BaseModel):
    caseId: str
    subjectId: str
    alertAt: datetime
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    transactions: List[Transaction] = Field(default_factory=list)
    similar: List[SimilarCase] = Field(default_factory=list)


class AuditEntry(BaseModel):
    id: str
    at: datetime
    caseId: str
    actionId: str
    label: str
    actor: str
    status: str
    error: Optional[str] = None
