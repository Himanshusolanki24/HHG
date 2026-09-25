"""Policy checks against the README's own rules. Run: python test_policy.py (or pytest)."""
from policy import Situation, needs_evidence, recommend, route


def acts(s):
    return {a["action"]: a["route"] for a in recommend(s)}


def test_routes():
    assert route("BLOCK_CARD", 2500) == "L1" and route("BLOCK_CARD", 2500.01) == "L2"
    assert route("FILE_REPORT", 10) == "L2" and route("DECLINE_TRANSACTION", 10) == "L1" and route("CREATE_CASE", 1e6) == "auto"


def test_r1_verify_before_block():
    a = acts(Situation("risk_score", 0.45, 1, "card_not_present_fraud", 100))
    assert "VERIFY_WITH_CUSTOMER" in a and "CREATE_CASE" in a and "BLOCK_CARD" not in a


def test_readme_flow_denial_then_block():
    s = Situation("risk_score", 0.45, 1, "card_not_present_fraud", 268.43)
    assert needs_evidence(s) == "customer_validation"
    s.response = "denied"
    a = acts(s)
    assert a["BLOCK_CARD"] == "L1" and "CREATE_CASE" in a and "FILE_REPORT" not in a


def test_r2_report_over_1000_or_shared():
    assert acts(Situation("customer_report", 0.9, 2, "undocumented", 1906.07, undocumented=True))["FILE_REPORT"] == "L2"
    a = acts(Situation("customer_report", 0.9, 2, "card_not_present_fraud", 50, connected_cards=["C1-K1"]))
    assert "FILE_REPORT" in a and "MONITOR_CONNECTED_CARDS" in a


def test_r3_confirmed_closes():
    a = acts(Situation("risk_score", 0.4, 1, "none", 0, response="confirmed"))
    assert "CLOSE_NO_FRAUD" in a and "BLOCK_CARD" not in a


def test_r7_recurring_dispute_never_blocks():
    s = Situation("customer_report", 0.2, 2, "none", 0, recurring_dispute=True)
    assert set(acts(s)) == {"CREATE_CASE", "VERIFY_WITH_CUSTOMER", "WARN_CUSTOMER"}
    s.response = "confirmed"
    assert "CLOSE_NO_FRAUD" in acts(s) and "BLOCK_CARD" not in acts(s)


def test_r6_shared_origin_reports_and_monitors():
    a = acts(Situation("analyst_request", 0.9, 3, "undocumented", 440, shared_origin="device X", undocumented=True, connected_cards=["A-K1", "B-K1"]))
    assert {"CREATE_CASE", "FILE_REPORT", "MONITOR_CONNECTED_CARDS", "ESCALATE_TO_ANALYST"} <= set(a)


def test_confident_legit_closes_without_asking():
    s = Situation("risk_score", 0.08, 3, "none", 0)
    assert needs_evidence(s) is None and set(acts(s)) == {"ALLOW_TRANSACTION", "CLOSE_NO_FRAUD"}


def test_never_block_all_cards():
    for p in (0.1, 0.5, 0.95):
        for r in (None, "denied", "confirmed", "no_reply"):
            assert "BLOCK_ALL_CARDS" not in acts(Situation("risk_score", p, 2, "card_not_present_fraud", 3000, response=r))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("policy: ok")
