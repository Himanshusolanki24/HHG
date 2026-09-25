"""Fraud Policy v1.0 (dataset README) as code. The LLM never picks actions or routes; this module does.

Every action carries the rule that produced it, so the answer file can cite it.
"""
from dataclasses import dataclass, field

AUTO = {
    "ALLOW_TRANSACTION", "MONITOR_CARD", "MONITOR_CONNECTED_CARDS", "WARN_CUSTOMER", "VERIFY_WITH_CUSTOMER",
    "STEP_UP_AUTH", "GENERATE_REPORT", "CREATE_CASE", "ESCALATE_TO_ANALYST", "CLOSE_NO_FRAUD",
}

RULES = {
    "R1": "Verify before you block on a weak signal: single signal and probability below 0.70 means VERIFY_WITH_CUSTOMER or STEP_UP_AUTH before any block.",
    "R2": "Customer denies the transaction: BLOCK_CARD and CREATE_CASE; add FILE_REPORT if exposure exceeds $1,000 or the case connects to a shared device profile or another card's fraud.",
    "R3": "Customer confirms the transaction: CLOSE_NO_FRAUD and note the confirmation in the case file.",
    "R4": "No reply within 24 hours: MONITOR_CARD and DECLINE_TRANSACTION for pending authorizations; escalate if exposure exceeds $500.",
    "R5": "Card testing: three or more small online authorizations within an hour, then a larger purchase: DECLINE_TRANSACTION and STEP_UP_AUTH; BLOCK_CARD if a purchase over $100 already cleared.",
    "R6": "Shared origin: several cards with fraud from one device profile, region or recipient email: CREATE_CASE, FILE_REPORT, MONITOR_CONNECTED_CARDS.",
    "R7": "Disputed but legitimate: dispute matches the customer's own recurring pattern: CREATE_CASE, VERIFY_WITH_CUSTOMER, WARN_CUSTOMER. Do not block.",
    "R8": "Uncertain verdict with exposure over $500, or conflicting evidence: ESCALATE_TO_ANALYST.",
    "R9": "Undocumented but coordinated abuse across customers: CREATE_CASE, FILE_REPORT, ESCALATE_TO_ANALYST.",
    "R10": "Never BLOCK_ALL_CARDS unless two of the customer's cards show confirmed fraud or credentials are confirmed compromised.",
    "3a": "Open a case at probability 0.30, whenever evidence is requested, or whenever a customer disputes a charge. File a report when fraud is confirmed or strongly suspected and exposure exceeds $1,000, or the activity connects to a shared device, region cluster or another customer's fraud, or the pattern is coordinated or undocumented.",
    "6": "Stop at probability >= 0.85 or <= 0.15 with two independent pieces of evidence, when verification settles it, or when further steps would not change the decision.",
}


def route(action: str, exposure: float) -> str:
    if action in AUTO:
        return "auto"
    if action == "DECLINE_TRANSACTION" or (action == "BLOCK_CARD" and exposure <= 2500):
        return "L1"
    return "L2"  # BLOCK_CARD > $2,500, BLOCK_ALL_CARDS, FILE_REPORT


@dataclass
class Situation:
    trigger: str  # risk_score | customer_report | analyst_request
    p: float
    n_evidence: int  # independent evidence items supporting the current lean
    pattern: str
    exposure: float
    recurring_dispute: bool = False  # R7
    shared_origin: str = ""  # R6: named shared element
    undocumented: bool = False  # R9
    card_testing: bool = False  # R5 shape observed
    cleared_over_100: bool = False
    connected_cards: list = field(default_factory=list)
    conflicting: bool = False
    response: str | None = None  # denied | confirmed | no_reply


def file_report(s: Situation, fraud: bool) -> bool:
    return fraud and (s.exposure > 1000 or bool(s.shared_origin) or bool(s.connected_cards) or s.undocumented)


def _acts(pairs, exposure):
    seen, out = set(), []
    for action, rule, why in pairs:
        if action not in seen:
            seen.add(action)
            out.append({"action": action, "route": route(action, exposure), "reason": f"{rule}: {why}"})
    return out


def recommend(s: Situation) -> list[dict]:
    """Actions for the current situation, ordered by what happens first."""
    a: list[tuple[str, str, str]] = []
    connected = [("MONITOR_CONNECTED_CARDS", "R6" if s.shared_origin else "R2", f"{len(s.connected_cards)} connected card(s) share the origin")] if s.connected_cards else []

    if s.recurring_dispute:
        if s.response == "confirmed":
            return _acts([("CREATE_CASE", "R7", "dispute recorded against the customer's recurring charge"),
                          ("CLOSE_NO_FRAUD", "R3", "customer recognised the recurring charge"),
                          ("WARN_CUSTOMER", "R7", "recurring charge reminder")], s.exposure)
        return _acts([("CREATE_CASE", "R7", "customer dispute on a charge matching their own recurring pattern"),
                      ("VERIFY_WITH_CUSTOMER", "R7", "confirm the recurring charge before any action"),
                      ("WARN_CUSTOMER", "R7", "recurring charge reminder; do not block")], s.exposure)

    denied = s.response == "denied" or (s.trigger == "customer_report" and s.response is None)
    if denied:
        fraud_exposure = s.exposure > 1000
        a += [("BLOCK_CARD", "R2", f"customer denies the transaction; exposure ${s.exposure:,.2f} "
               f"{'<=' if s.exposure <= 2500 else '>'} $2,500"),
              ("CREATE_CASE", "R2", "customer dispute")]
        if s.shared_origin or s.undocumented or fraud_exposure or s.connected_cards:
            why = "exposure over $1,000" if fraud_exposure else f"shared origin: {s.shared_origin}" if s.shared_origin else "coordinated pattern" if s.undocumented else "connected to another card's fraud"
            a.append(("FILE_REPORT", "R2", why))
        if s.undocumented:
            a.append(("ESCALATE_TO_ANALYST", "R9", "pattern fits no documented typology"))
        return _acts(a + connected, s.exposure)

    if s.response == "confirmed":
        return _acts([("ALLOW_TRANSACTION", "R3", "customer confirmed the transaction"),
                      ("CLOSE_NO_FRAUD", "R3", "confirmation noted in the case file")], s.exposure)
    if s.response == "no_reply":
        a = [("MONITOR_CARD", "R4", "no reply within 24 hours"), ("DECLINE_TRANSACTION", "R4", "pending authorizations declined")]
        if s.exposure > 500:
            a.append(("ESCALATE_TO_ANALYST", "R4", f"exposure ${s.exposure:,.2f} exceeds $500"))
        return _acts(a, s.exposure)

    # No customer statement yet. Nothing in the policy allows a block on graph evidence alone (except R5),
    # so strong cases hold the authorization and verify; the block follows the denial under R2.
    if s.p <= 0.15 and s.n_evidence >= 2:
        return _acts([("ALLOW_TRANSACTION", "6", f"probability {s.p:.2f} <= 0.15 on {s.n_evidence} independent signals"),
                      ("CLOSE_NO_FRAUD", "6", "alert explained by the cardholder's own behaviour")], s.exposure)
    if s.card_testing:
        a += [("BLOCK_CARD", "R5", "purchase over $100 already cleared") if s.cleared_over_100 else ("DECLINE_TRANSACTION", "R5", "testing sequence observed"),
              ("STEP_UP_AUTH", "R5", "confirm the cardholder before further activity")]
    elif s.p >= 0.70 and s.n_evidence >= 2:
        a += [("DECLINE_TRANSACTION", "R1", f"probability {s.p:.2f} on {s.n_evidence} signals; hold the authorization"),
              ("VERIFY_WITH_CUSTOMER", "R1", "confirm with the cardholder before any block")]
    else:
        a.append(("VERIFY_WITH_CUSTOMER", "R1", f"probability {s.p:.2f} on {'a single signal' if s.n_evidence <= 1 else f'{s.n_evidence} signals'}; verify before any block"))
    a.append(("CREATE_CASE", "3a", "evidence requested" if s.p < 0.30 else f"fraud probability {s.p:.2f} >= 0.30"))
    if s.shared_origin:
        a += [("FILE_REPORT", "R6", f"shared origin: {s.shared_origin}")]
    if s.undocumented:
        a += [("FILE_REPORT", "R9", "coordinated undocumented pattern"), ("ESCALATE_TO_ANALYST", "R9", "pattern fits no documented typology")]
    elif (s.exposure > 500 and 0.3 < s.p < 0.7) or s.conflicting:
        a.append(("ESCALATE_TO_ANALYST", "R8", "evidence conflicts" if s.conflicting else f"uncertain with exposure ${s.exposure:,.2f} over $500"))
    return _acts(a + connected, s.exposure)


def needs_evidence(s: Situation) -> str | None:
    """Which controlled request the policy calls for, if any (README §5, rule 6 stopping)."""
    if s.recurring_dispute:
        return "customer_validation"
    if s.trigger == "customer_report":
        return None  # the customer already answered: they deny it
    if s.p <= 0.15 and s.n_evidence >= 2:
        return None  # stop rule: settled as legitimate
    return "customer_validation"  # blocking needs the cardholder's denial (R2); verifying is auto-approved


if __name__ == "__main__":
    # Smoke self-check; full cases in test_policy.py.
    print(recommend(Situation("risk_score", 0.45, 1, "card_not_present_fraud", 100.0)))
