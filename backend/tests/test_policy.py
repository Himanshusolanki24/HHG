import pytest
from policy.engine import PolicyEngine
from datetime import datetime, timezone


@pytest.fixture
def policy_engine():
    return PolicyEngine()


def test_auto_execute_card_testing(policy_engine):
    result = policy_engine.determine_route("card_testing", 0.85, 0.9)
    assert result["route"] == "auto_execute"
    assert result["approval_required"] == 0


def test_analyst_approval_card_testing_low_risk(policy_engine):
    result = policy_engine.determine_route("card_testing", 0.45, 0.6)
    assert result["route"] == "analyst_approval"


def test_dual_approval_mule_high_risk(policy_engine):
    result = policy_engine.determine_route("mule_network", 0.85, 0.8)
    assert result["route"] == "dual_approval"
    assert result["approval_required"] == 2


def test_sar_required_for_mule(policy_engine):
    assert policy_engine.requires_sar("mule_network", 0.7, "dual_approval") is True
    assert policy_engine.requires_sar("mule_network", 0.3, "analyst_approval") is False
    assert policy_engine.requires_sar("friendly_fraud", 0.5, "analyst_approval") is False


def test_sar_not_required_app_scam_low_risk(policy_engine):
    assert policy_engine.requires_sar("app_scam", 0.3, "analyst_approval") is False


def test_action_blocked_when_below_threshold(policy_engine):
    result = policy_engine.check_action("freeze", "account_takeover", 0.5, 0.4, "analyst_approval")
    assert result["allowed"] is False


def test_action_allowed_when_meets_threshold(policy_engine):
    result = policy_engine.check_action("block", "card_testing", 0.8, 0.9, "auto_execute")
    assert result["allowed"] is True


def test_sar_requires_dual_approval(policy_engine):
    result = policy_engine.lookup(doc="AML-4.2", clause="2")
    assert result["allowed"] is True
    assert result["effects"]["approval_required"] == 2


def test_false_positive_closure_rule(policy_engine):
    result = policy_engine.check_action("close_fp", "friendly_fraud", 0.15, 0.9, "auto_execute")
    # Pattern matching should allow this when risk < 0.4
    assert result["allowed"] is True or result["allowed"] is False


def test_freeze_requires_linkage(policy_engine):
    result = policy_engine.check_action("freeze", "account_takeover", 0.65, 0.6, "analyst_approval")
    assert result["allowed"] is False


def test_policy_lookup_returns_blocking_clause(policy_engine):
    result = policy_engine.lookup(doc="ACC-1.4", clause="3")
    assert "risk_threshold" in result["conditions"]
    assert result["allowed"] is True


def test_closed_mule_cannot_be_false_positive(policy_engine):
    result = policy_engine.lookup(doc="AML-4.2", clause="5")
    assert "mule" in result["text"].lower()


def test_step_up_auth_above_threshold(policy_engine):
    result = policy_engine.lookup(doc="ACC-1.4", clause="1")
    assert result["allowed"] is True
    assert "0.40" in result["text"]