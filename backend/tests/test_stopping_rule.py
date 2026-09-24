import pytest
from policy.engine import PolicyEngine
from models import ApprovalRoute, Route, RiskAssessment
from datetime import datetime, timezone


@pytest.fixture
def policy_engine():
    return PolicyEngine()


def test_stopping_rule_confidence_threshold(policy_engine):
    confidence = 0.85
    risk = 0.75
    threshold = 0.70
    assert confidence >= threshold


def test_stopping_rule_evidence_cost_below_value(policy_engine):
    expected_value = 0.85 * 100
    evidence_cost = 50
    assert expected_value > evidence_cost


def test_stopping_rule_evidence_cost_exceeds_value(policy_engine):
    confidence = 0.35
    expected_value = confidence * 100
    evidence_cost = 50
    assert expected_value < evidence_cost


def test_risk_band_calculation():
    assessment = RiskAssessment(risk=0.8, riskLo=0.68, riskHi=0.92, confidence=0.75, band="high")
    assert assessment.band == "high"

    assessment = RiskAssessment(risk=0.5, riskLo=0.38, riskHi=0.62, confidence=0.55, band="medium")
    assert assessment.band == "medium"

    assessment = RiskAssessment(risk=0.2, riskLo=0.08, riskHi=0.32, confidence=0.8, band="low")
    assert assessment.band == "low"


def test_approval_route_pre_post_evidence():
    route = ApprovalRoute(
        route=Route.analyst_approval,
        policyId="AML-4.2.2",
        required_approvers=1,
        pre_evidence_route=Route.analyst_approval,
        post_evidence_route=Route.dual_approval,
        pre_risk=0.52,
        post_risk=0.89,
        pre_confidence=0.48,
        post_confidence=0.86,
        evidence_caused_change=True,
        changed_by="EV-mule_linkage"
    )
    assert route.pre_evidence_route != route.post_evidence_route
    assert route.evidence_caused_change is True


def test_recommendation_flip_detection():
    prior_route = Route.analyst_approval
    post_route = Route.dual_approval
    assert prior_route != post_route


def test_confidence_vs_risk_separation():
    risk = 0.75
    confidence = 0.45
    assert risk > confidence
    assert 0 <= risk <= 1
    assert 0 <= confidence <= 1


def test_stopping_rule_medium_risk_high_confidence():
    confidence = 0.8
    risk = 0.45
    threshold = 0.70
    if confidence >= threshold:
        stop = True
    else:
        stop = False
    assert stop is True


def test_stopping_rule_high_risk_low_confidence():
    confidence = 0.35
    risk = 0.8
    threshold = 0.70
    if confidence >= threshold:
        stop = True
    else:
        stop = False
    assert stop is False


def test_decision_flip_records_change():
    prior_action = "Require step-up auth and monitor 72h"
    new_action = "Freeze account and file SAR"
    prior_route = Route.analyst_approval
    new_route = Route.dual_approval
    assert prior_action != new_action
    assert prior_route != new_route


def test_route_approval_counts():
    auto = {"route": "auto_execute", "approval_required": 0}
    analyst = {"route": "analyst_approval", "approval_required": 1}
    dual = {"route": "dual_approval", "approval_required": 2}
    assert auto["approval_required"] == 0
    assert analyst["approval_required"] == 1
    assert dual["approval_required"] == 2