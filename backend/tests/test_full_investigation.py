import pytest
from policy.engine import PolicyEngine
from fixtures.cases import load_cases, load_investigation
from models import AnswerFile, CaseRecord, Recommendation, ApprovalRoute, Evidence, RiskAssessment
from datetime import datetime, timezone
import sys
import os
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_full_investigation_fc1042_recommendation_flip():
    cases = load_cases()
    case = next(c for c in cases if c["id"] == "FC-1042")
    investigation = load_investigation("FC-1042")

    assert case["id"] == "FC-1042"
    assert investigation is not None
    assert len(investigation["steps"]) == 11

    prior_rec = None
    post_rec = None
    for step in investigation["steps"]:
        if step.get("tool") == "recommend" and step.get("recommendation"):
            rec = step["recommendation"]
            if prior_rec is None:
                prior_rec = rec
            else:
                post_rec = rec

    assert prior_rec is not None
    assert post_rec is not None
    assert prior_rec["action"] != post_rec["action"]
    assert prior_rec["route"] != post_rec["route"]
    assert post_rec["route"] == "dual_approval"
    assert prior_rec["route"] == "analyst_approval"


def test_full_investigation_fc1041_auto_execute():
    cases = load_cases()
    case = next(c for c in cases if c["id"] == "FC-1041")
    investigation = load_investigation("FC-1041")

    prior_rec = None
    post_rec = None
    for step in investigation["steps"]:
        if step.get("tool") == "recommend" and step.get("recommendation"):
            rec = step["recommendation"]
            if prior_rec is None:
                prior_rec = rec
            else:
                post_rec = rec

    assert prior_rec is not None and post_rec is not None
    assert prior_rec["route"] == "analyst_approval"
    assert post_rec["route"] == "auto_execute"


def test_answer_file_contains_all_required_fields():
    from batch import build_answer_file
    cases = load_cases()
    case = cases[0]
    answer = build_answer_file(case, load_investigation(case["id"]))

    assert answer.case.id == case["id"]
    assert answer.recommendation is not None
    assert answer.approval_route is not None
    assert answer.risk_assessment is not None
    assert isinstance(answer.risk_assessment.risk, float)
    assert isinstance(answer.risk_assessment.confidence, float)
    assert 0 <= answer.risk_assessment.risk <= 1
    assert 0 <= answer.risk_assessment.confidence <= 1


def test_answer_file_approval_route_recorded_twice():
    from batch import build_answer_file
    cases = load_cases()
    case = next(c for c in cases if c["id"] == "FC-1042")
    answer = build_answer_file(case, load_investigation("FC-1042"))

    ar = answer.approval_route
    assert ar.pre_evidence_route is not None
    assert ar.post_evidence_route is not None
    assert ar.pre_risk is not None
    assert ar.post_risk is not None


def test_answer_file_contains_sar_when_required():
    from batch import build_answer_file
    cases = load_cases()
    case = next(c for c in cases if c["pattern"] == "mule_network")
    answer = build_answer_file(case, load_investigation(case["id"]))

    if case["risk"] >= 0.5:
        assert answer.sar is not None


def test_all_20_cases_have_answer_files():
    from batch import build_answer_file
    cases = load_cases()
    assert len(cases) == 20

    for case in cases:
        answer = build_answer_file(case, load_investigation(case["id"]))
        assert answer.case.id == case["id"]
        assert answer.recommendation is not None
        assert answer.approval_route is not None


def test_evidence_has_source_references():
    from batch import build_answer_file
    cases = load_cases()
    case = cases[0]
    answer = build_answer_file(case, load_investigation(case["id"]))

    for ev in answer.evidence:
        assert ev.source is not None and ev.source != ""
        assert ev.id is not None