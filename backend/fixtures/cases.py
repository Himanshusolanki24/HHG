"""Load case fixtures from the frontend fixture data."""
import json
import os
from pathlib import Path
from datetime import datetime

FIXTURES_DIR = Path(__file__).parent / "frontend_fixtures"

def load_cases() -> list[dict]:
    path = FIXTURES_DIR / "cases.json"
    if not path.exists():
        # Fall back to inline data
        return _inline_cases()
    with open(path) as f:
        return json.load(f)


def load_policies() -> list[dict]:
    path = FIXTURES_DIR / "policies.json"
    if not path.exists():
        return _inline_policies()
    with open(path) as f:
        return json.load(f)


def load_investigation(case_id: str) -> dict | None:
    path = FIXTURES_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _inline_cases() -> list[dict]:
    return [
        {"id":"FC-1041","title":"Micro-auth burst on card ••4471","trigger":"risk_score","pattern":"card_testing","status":"open","risk":0.84,"confidence":0.72,"stateSince":"2026-09-24T08:41:00Z","hasRun":True},
        {"id":"FC-1042","title":"Fan-in then crypto cash-out, acct ••5530","trigger":"analyst_request","pattern":"mule_network","status":"open","risk":0.52,"confidence":0.48,"stateSince":"2026-09-24T07:53:00Z","hasRun":True},
        {"id":"FC-1043","title":"Bank-impersonation transfer, acct ••3907","trigger":"customer_report","pattern":"app_scam","status":"open","risk":0.81,"confidence":0.77,"stateSince":"2026-09-24T09:31:00Z","hasRun":True},
        {"id":"FC-1044","title":"New device, password reset, payee added","trigger":"risk_score","pattern":"account_takeover","status":"awaiting_evidence","risk":0.71,"confidence":0.55,"stateSince":"2026-09-24T06:12:00Z","hasRun":False},
        {"id":"FC-1045","title":"Thin-file applicant, shared SSN prefix","trigger":"risk_score","pattern":"synthetic_identity","status":"open","risk":0.63,"confidence":0.41,"stateSince":"2026-09-24T05:40:00Z","hasRun":False},
        {"id":"FC-1046","title":"Chargeback on delivered electronics","trigger":"customer_report","pattern":"friendly_fraud","status":"ready_to_act","risk":0.28,"confidence":0.83,"stateSince":"2026-09-23T22:05:00Z","hasRun":False},
        {"id":"FC-1047","title":"Card tested at 3 donation sites","trigger":"risk_score","pattern":"card_testing","status":"closed","risk":0.91,"confidence":0.9,"stateSince":"2026-09-23T19:48:00Z","hasRun":False},
        {"id":"FC-1048","title":"Romance-scam wire, second instalment","trigger":"customer_report","pattern":"app_scam","status":"awaiting_evidence","risk":0.76,"confidence":0.62,"stateSince":"2026-09-24T08:02:00Z","hasRun":False},
        {"id":"FC-1049","title":"Student account receiving 11 transfers","trigger":"analyst_request","pattern":"mule_network","status":"open","risk":0.67,"confidence":0.58,"stateSince":"2026-09-24T07:15:00Z","hasRun":False},
        {"id":"FC-1050","title":"SIM swap preceding login from new ASN","trigger":"risk_score","pattern":"account_takeover","status":"ready_to_act","risk":0.88,"confidence":0.81,"stateSince":"2026-09-24T04:30:00Z","hasRun":False},
        {"id":"FC-1051","title":"Disputed subscription renewals","trigger":"customer_report","pattern":"friendly_fraud","status":"closed","risk":0.19,"confidence":0.88,"stateSince":"2026-09-23T16:20:00Z","hasRun":False},
        {"id":"FC-1052","title":"Address shared by 7 new applicants","trigger":"analyst_request","pattern":"synthetic_identity","status":"awaiting_evidence","risk":0.69,"confidence":0.5,"stateSince":"2026-09-24T03:55:00Z","hasRun":False},
        {"id":"FC-1053","title":"Invoice redirection on business account","trigger":"customer_report","pattern":"app_scam","status":"open","risk":0.73,"confidence":0.66,"stateSince":"2026-09-24T09:05:00Z","hasRun":False},
        {"id":"FC-1054","title":"Low-value auths from headless browser","trigger":"risk_score","pattern":"card_testing","status":"ready_to_act","risk":0.86,"confidence":0.79,"stateSince":"2026-09-24T02:18:00Z","hasRun":False},
        {"id":"FC-1055","title":"Dormant account reactivated, rapid outflow","trigger":"risk_score","pattern":"mule_network","status":"open","risk":0.58,"confidence":0.44,"stateSince":"2026-09-24T08:50:00Z","hasRun":False},
        {"id":"FC-1056","title":"Email changed from unfamiliar locale","trigger":"risk_score","pattern":"account_takeover","status":"closed","risk":0.34,"confidence":0.8,"stateSince":"2026-09-23T13:10:00Z","hasRun":False},
        {"id":"FC-1057","title":"Credit builder loop across 4 issuers","trigger":"analyst_request","pattern":"synthetic_identity","status":"open","risk":0.61,"confidence":0.39,"stateSince":"2026-09-24T01:42:00Z","hasRun":False},
        {"id":"FC-1058","title":"Refund claimed after merchant confirmation","trigger":"customer_report","pattern":"friendly_fraud","status":"awaiting_evidence","risk":0.31,"confidence":0.6,"stateSince":"2026-09-24T07:33:00Z","hasRun":False},
        {"id":"FC-1059","title":"Overpayment refund to third-party account","trigger":"analyst_request","pattern":"app_scam","status":"ready_to_act","risk":0.79,"confidence":0.74,"stateSince":"2026-09-24T06:48:00Z","hasRun":False},
        {"id":"FC-1060","title":"Cash-app transfers split under threshold","trigger":"risk_score","pattern":"mule_network","status":"open","risk":0.47,"confidence":0.35,"stateSince":"2026-09-24T09:20:00Z","hasRun":False},
    ]


def _inline_policies() -> list[dict]:
    return [
        {"id":"CARD-2.1.3","doc":"CARD-2.1","clause":"3","title":"Automated card block","text":"A card may be blocked and reissued without analyst approval when 10 or more authorizations under $2 occur within 15 minutes and at least one originates from an anonymizing network."},
        {"id":"CARD-2.1.5","doc":"CARD-2.1","clause":"5","title":"Card-not-present release","text":"A blocked card may only be released after the cardholder passes step-up verification through a registered device."},
        {"id":"ACC-1.4.1","doc":"ACC-1.4","clause":"1","title":"Step-up authentication","text":"Any analyst may require step-up authentication on an account with model risk of 0.40 or higher."},
        {"id":"ACC-1.4.3","doc":"ACC-1.4","clause":"3","title":"Account freeze threshold","text":"An account may be frozen only when model risk is 0.70 or higher with confidence of 0.75 or higher, or when graph linkage to a confirmed fraud case is established."},
        {"id":"AML-4.2.2","doc":"AML-4.2","clause":"2","title":"SAR filing","text":"Suspicious activity reports require dual approval: the investigating analyst and an MLRO delegate. SAR filing cannot be triggered while the recommended route is single approval."},
        {"id":"AML-4.2.5","doc":"AML-4.2","clause":"5","title":"Closure restriction","text":"Cases with confirmed linkage to a mule network may not be closed as false positive without MLRO review."},
        {"id":"APP-3.1.4","doc":"APP-3.1","clause":"4","title":"Payment recall","text":"Analysts may initiate a funds recall and request a beneficiary hold when the customer reports authorized push-payment fraud within 24 hours of the payment."},
        {"id":"APP-3.1.6","doc":"APP-3.1","clause":"6","title":"Reimbursement","text":"Reimbursement over $1,000 requires dual approval and a completed recall attempt."},
        {"id":"GEN-0.2.1","doc":"GEN-0.2","clause":"1","title":"Enhanced monitoring","text":"Any analyst may place an account under enhanced monitoring for up to 30 days."},
        {"id":"GEN-0.2.4","doc":"GEN-0.2","clause":"4","title":"False-positive closure","text":"A case may be closed as false positive by one analyst when model risk is below 0.40 and no unresolved high-gain unknowns remain."},
    ]
