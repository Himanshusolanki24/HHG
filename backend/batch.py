import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from models import (
    CaseRecord, Evidence, AgentStep, RiskAssessment, Recommendation,
    ApprovalRoute, SAR, AnswerFile, Trigger, Pattern, CaseStatus, Route,
    Unknown, ActionOption
)
from fixtures.cases import load_cases, load_policies, load_investigation


def get_case_data(case: dict) -> dict | None:
    inv = load_investigation(case["id"])
    return inv


def compute_risk_assessment(case: dict) -> RiskAssessment:
    risk = case["risk"]
    confidence = case["confidence"]
    if risk >= 0.7:
        band = "high"
    elif risk >= 0.4:
        band = "medium"
    else:
        band = "low"
    margin = 0.12
    return RiskAssessment(
        risk=risk,
        riskLo=max(0, risk - margin),
        riskHi=min(1, risk + margin),
        confidence=confidence,
        band=band
    )


def compute_approval_route(
    case: dict,
    prior_recommendation: Optional[Recommendation] = None,
    new_evidence_received: bool = False
) -> ApprovalRoute:
    pattern = case["pattern"]
    risk = case["risk"]
    confidence = case["confidence"]

    if pattern == "card_testing":
        if risk >= 0.7:
            route = Route.auto_execute
        elif risk >= 0.4:
            route = Route.analyst_approval
        else:
            route = Route.analyst_approval
        policy_id = "CARD-2.1.3"
    elif pattern == "mule_network":
        if risk >= 0.7:
            route = Route.dual_approval
        else:
            route = Route.analyst_approval
        policy_id = "AML-4.2.2"
    elif pattern == "app_scam":
        if risk >= 0.7:
            route = Route.analyst_approval
        else:
            route = Route.analyst_approval
        policy_id = "APP-3.1.4"
    elif pattern == "account_takeover":
        if risk >= 0.7 and confidence >= 0.75:
            route = Route.dual_approval
        elif risk >= 0.4:
            route = Route.analyst_approval
        else:
            route = Route.analyst_approval
        policy_id = "ACC-1.4.1"
    elif pattern == "synthetic_identity":
        route = Route.analyst_approval
        policy_id = "ACC-1.4.3"
    elif pattern == "friendly_fraud":
        if risk < 0.4:
            route = Route.auto_execute
        else:
            route = Route.analyst_approval
        policy_id = "GEN-0.2.4"
    else:
        route = Route.analyst_approval
        policy_id = "GEN-0.2.1"

    pre_route = route
    pre_risk = risk
    pre_confidence = confidence
    post_route = route
    post_risk = risk
    post_confidence = confidence
    changed_by = None
    evidence_caused_change = False

    if new_evidence_received and (prior_recommendation is not None or True):
        if pattern == "mule_network":
            post_risk = min(1.0, risk + 0.37)
        elif pattern == "card_testing":
            post_risk = min(1.0, risk + 0.12)
        else:
            post_risk = min(1.0, risk + 0.15)
        post_confidence = min(1.0, confidence + 0.12)
        if post_risk >= 0.7 and pattern == "mule_network":
            post_route = Route.dual_approval
            evidence_caused_change = True
            changed_by = "EV-mule_linkage"
        elif post_risk >= 0.7 and pattern == "card_testing":
            post_route = Route.auto_execute
            evidence_caused_change = True
            changed_by = "EV-compromise_confirmed"
        elif post_risk >= 0.7 and pattern == "account_takeover":
            post_route = Route.dual_approval
            evidence_caused_change = True
            changed_by = "EV-device_linkage"

    return ApprovalRoute(
        route=route,
        policyId=policy_id,
        required_approvers=2 if route == Route.dual_approval else 1,
        pre_evidence_route=pre_route,
        post_evidence_route=post_route,
        pre_risk=pre_risk,
        post_risk=post_risk,
        pre_confidence=pre_confidence,
        post_confidence=post_confidence,
        evidence_caused_change=evidence_caused_change,
        changed_by=changed_by
    )


def build_recommendation(
    case: dict,
    evidence_ids: list[str],
    approval_route: ApprovalRoute,
    step_count: int = 1
) -> Recommendation:
    risk = case["risk"]
    confidence = case["confidence"]
    pattern = case["pattern"]
    case_id = case["id"]

    margin = 0.12
    actions = []

    if pattern == "card_testing":
        actions = [
            ActionOption(id="block_card", label="Block and reissue card", allowed=True, policyId="CARD-2.1.3"),
            ActionOption(id="step_up", label="Require step-up auth", allowed=True, policyId="ACC-1.4.1"),
            ActionOption(id="release", label="Release held payment", allowed=False, policyId="CARD-2.1.5", reason="Release needs step-up verification on a registered device"),
            ActionOption(id="close_fp", label="Close as false positive", allowed=False, policyId="GEN-0.2.4", reason="Risk is above 0.40"),
        ]
    elif pattern == "mule_network":
        actions = [
            ActionOption(id="step_up", label="Require step-up auth", allowed=True, policyId="ACC-1.4.1"),
            ActionOption(id="monitor", label="Monitor 72h", allowed=True, policyId="GEN-0.2.1"),
            ActionOption(id="freeze", label="Freeze account", allowed=risk >= 0.7, policyId="ACC-1.4.3", reason="Risk and confidence must meet freeze threshold"),
            ActionOption(id="file_sar", label="File SAR", allowed=approval_route.route == Route.dual_approval, policyId="AML-4.2.2", reason="SAR requires dual approval"),
            ActionOption(id="close_fp", label="Close as false positive", allowed=False, policyId="AML-4.2.5", reason="Mule-network linkage needs MLRO review"),
        ]
    elif pattern == "app_scam":
        actions = [
            ActionOption(id="recall", label="Initiate recall", allowed=True, policyId="APP-3.1.4"),
            ActionOption(id="block_payee", label="Block payee", allowed=True, policyId="APP-3.1.4"),
            ActionOption(id="reimburse", label="Reimburse", allowed=False, policyId="APP-3.1.6", reason="Reimbursement over $1,000 requires dual approval and completed recall"),
        ]
    else:
        actions = [
            ActionOption(id="monitor", label="Enhanced monitoring", allowed=True, policyId="GEN-0.2.1"),
            ActionOption(id="close_fp", label="Close as false positive", allowed=risk < 0.4, policyId="GEN-0.2.4"),
        ]

    rationale = f"{pattern.replace('_', ' ').title} investigation on {case['subjectId'] if case.get('subjectId') else case['id']}. "
    rationale += f"Risk score {risk:.2f}, confidence {confidence:.2f}. Evidence items: {len(evidence_ids)}."

    unknowns = [
        Unknown(
            id=f"u-{case_id}-{i}",
            question=f"Unknown {i+1} for {case_id}",
            resolvedBy="pending",
            infoGain=0.3,
            resolved=False
        )
        for i in range(2)
    ]

    return Recommendation(
        id=f"R-{case_id}-{step_count}",
        action=actions[0].label if actions else "Monitor",
        route=approval_route.route,
        policyId=approval_route.policyId,
        risk=risk,
        riskLo=max(0, risk - margin),
        riskHi=min(1, risk + margin),
        confidence=confidence,
        rationale=rationale,
        unknowns=unknowns,
        actions=actions,
        causedBy=evidence_ids
    )


def build_sar(case: dict, recommendation: Recommendation) -> Optional[SAR]:
    pattern = case["pattern"]
    risk = case["risk"]
    if pattern in ("mule_network", "app_scam") and risk >= 0.5:
        return SAR(
            id=f"SAR-{case['id']}",
            case_id=case["id"],
            filed_at=datetime.now(timezone.utc),
            filing_officer="system.agent",
            mlro_delegate=None,
            status="pending" if recommendation.route != Route.dual_approval else "pending_dual_approval",
            reason=f"Pattern {pattern} with risk {risk:.2f}",
            risk_score=risk,
            policy_clause="AML-4.2.2",
            evidence_summary=f"Case involves {pattern} pattern. Risk {risk:.2f}."
        )
    return None


def build_case_record(case: dict, evidence: list[Evidence], investigation: dict | None) -> CaseRecord:
    approval_route = compute_approval_route(case)
    recommendation = build_recommendation(case, [e.id for e in evidence], approval_route)
    sar = build_sar(case, recommendation)

    subject_id = None
    if investigation:
        subject_id = investigation.get("subjectId")
    elif case.get("trigger") == "risk_score":
        subject_id = f"acc:{case['id'].split('-')[1]}"
    else:
        subject_id = f"acc:{case['id'].split('-')[1]}"

    findings = [f"Pattern detected: {case['pattern']}", f"Risk score: {case['risk']:.2f}", f"Trigger: {case['trigger']}"]
    decisions = [f"Initial assessment: {case['pattern']} pattern confirmed"]
    actions = [r.label for r in recommendation.actions if r.allowed]

    status = CaseStatus(case["status"]) if case["status"] in [s.value for s in CaseStatus] else CaseStatus.open

    return CaseRecord(
        id=case["id"],
        title=case["title"],
        trigger=Trigger(case["trigger"]),
        pattern=Pattern(case["pattern"]),
        status=status,
        risk=case["risk"],
        confidence=case["confidence"],
        stateSince=datetime.fromisoformat(case["stateSince"].replace("Z", "+00:00")),
        hasRun=case.get("hasRun", False),
        subjectId=subject_id,
        investigation_trail=[],
        evidence=evidence,
        findings=findings,
        decisions=decisions,
        actions=actions,
        recommendation=recommendation,
        approval_route=approval_route,
        sar=sar,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )


def build_answer_file(case: dict, investigation: dict | None) -> AnswerFile:
    case_data = investigation or {}
    evidence = []
    if investigation and "steps" in investigation:
        for step in investigation.get("steps", []):
            if step.get("evidence"):
                ev = step["evidence"]
                evidence.append(evidence_from_dict(ev))

    rec_approval_pre = compute_approval_route(case)
    rec_approval_post = compute_approval_route(case, new_evidence_received=True)

    recommendation = build_recommendation(case, [e.id for e in evidence], rec_approval_pre)

    approval_route = ApprovalRoute(
        route=rec_approval_pre.route,
        policyId=rec_approval_pre.policyId,
        required_approvers=rec_approval_pre.required_approvers,
        pre_evidence_route=rec_approval_pre.route,
        post_evidence_route=rec_approval_post.post_evidence_route,
        pre_risk=rec_approval_pre.pre_risk,
        post_risk=rec_approval_post.post_risk,
        pre_confidence=rec_approval_pre.pre_confidence,
        post_confidence=rec_approval_post.post_confidence,
        evidence_caused_change=rec_approval_pre.route != rec_approval_post.post_evidence_route,
        changed_by="new_evidence" if rec_approval_pre.route != rec_approval_post.post_evidence_route else None
    )

    sar = build_sar(case, recommendation)

    case_record = build_case_record(case, evidence, investigation)
    case_record.approval_route = approval_route
    case_record.recommendation = recommendation
    case_record.sar = sar
    case_record.investigation_trail = []

    return AnswerFile(
        case=case_record,
        evidence=evidence,
        findings=case_record.findings,
        decisions=case_record.decisions,
        actions=case_record.actions,
        recommendation=recommendation,
        approval_route=approval_route,
        sar=sar,
        risk_assessment=RiskAssessment(
            risk=case["risk"],
            riskLo=max(0, case["risk"] - 0.12),
            riskHi=min(1, case["risk"] + 0.12),
            confidence=case["confidence"],
            band="high" if case["risk"] >= 0.7 else ("medium" if case["risk"] >= 0.4 else "low")
        ),
        generated_at=datetime.now(timezone.utc)
    )


def evidence_from_dict(d: dict) -> Evidence:
    return Evidence(
        id=d["id"],
        kind=d.get("kind", "graph"),
        label=d.get("label", ""),
        summary=d.get("summary", ""),
        source=d.get("source", ""),
        nodes=d.get("nodes", []),
        edges=d.get("edges", [])
    )


def run_batch(output_dir: str | None = None):
    os.makedirs(output_dir or config().answers_dir, exist_ok=True)
    cases = load_cases()
    answers = []

    for case in cases:
        investigation = load_investigation(case["id"])
        answer = build_answer_file(case, investigation)

        output_path = Path(output_dir or config().answers_dir) / f"{case['id']}_answer.json"
        answer_dict = answer.model_dump()
        with open(output_path, "w") as f:
            json.dump(answer_dict, f, indent=2, default=str)

        answers.append(answer)
        print(f"Generated answer file: {case['id']} -> {output_path.name}")

    print(f"\nBatch complete: {len(answers)} answer files generated.")
    return answers


def config():
    from config import Config
    return Config()


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else None
    run_batch(output)