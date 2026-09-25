"""Checks every answer file against the README's Answer Format and policy. Run: python validate.py"""
import json
import sys
from pathlib import Path

from data import Store
from policy import route

ACTIONS = {"ALLOW_TRANSACTION", "DECLINE_TRANSACTION", "MONITOR_CARD", "MONITOR_CONNECTED_CARDS", "WARN_CUSTOMER",
           "VERIFY_WITH_CUSTOMER", "STEP_UP_AUTH", "BLOCK_CARD", "BLOCK_ALL_CARDS", "GENERATE_REPORT", "CREATE_CASE",
           "FILE_REPORT", "ESCALATE_TO_ANALYST", "CLOSE_NO_FRAUD"}
PATTERNS = {"card_testing", "card_not_present_fraud", "card_not_present_new_device", "out_of_region_use", "account_takeover", "undocumented", "none"}
CASES = Path(__file__).parent.parent / "cases"


def check(a: dict, st: Store) -> list[str]:
    err, c, sar, nba = [], a["case"], a["sar"], a["next_best_actions"]
    txns = set(st.tx["TransactionID"].astype(str))
    cards = set(st.tx["card_id"])
    closed = set(st.closed["case_id"])
    for k in ("case_id", "case", "evidence_requests", "next_best_actions", "sar", "stop_reason", "tool_calls", "tokens", "latency_s"):
        err += [f"missing {k}"] if k not in a else []
    texts = {"summary": c["summary"], "pattern_description": c["pattern_description"], "sar.narrative": sar["narrative"],
             "sar.reason": sar["reason"], "what_changed": nba["what_changed"], "stop_reason": a["stop_reason"]}
    err += [f"{k} must be a plain string" for k, v in texts.items() if not isinstance(v, str)]
    err += [f"{k} contains markdown" for k, v in texts.items() if isinstance(v, str) and "**" in v]
    err += [f"bad status {c['status']}"] if c["status"] not in {"open", "closed_fraud", "closed_legitimate", "escalated"} else []
    err += [f"bad verdict {c['verdict']}"] if c["verdict"] not in {"fraud", "legitimate", "uncertain"} else []
    err += [f"bad pattern {c['pattern']}"] if c["pattern"] not in PATTERNS else []
    err += ["undocumented needs pattern_description"] if (c["pattern"] == "undocumented") != bool(c["pattern_description"]) else []
    err += [f"unknown txn {t}" for t in c["affected_txn_ids"] if t not in txns]
    err += [f"unknown card {x}" for x in c["connected_card_ids"] if x not in cards]
    err += [f"unknown closed case {x}" for x in c["similar_prior_cases"] if x not in closed]
    amt = st.tx.set_index(st.tx["TransactionID"].astype(str))["TransactionAmt"]
    total = round(float(amt.reindex(c["affected_txn_ids"]).abs().sum()), 2)
    err += [f"exposure {c['exposure_usd']} != sum {total}"] if abs(total - c["exposure_usd"]) > 0.01 else []
    if c["verdict"] == "legitimate":
        err += ["legitimate must have no affected txns / exposure / SAR"] if c["affected_txn_ids"] or c["exposure_usd"] or sar["file"] else []
    err += [f"first_suspicious not in affected"] if c["affected_txn_ids"] and c["first_suspicious_txn_id"] not in c["affected_txn_ids"] else []
    for stage in ("initial", "final"):
        for x in nba[stage]:
            err += [f"{stage}: unknown action {x['action']}"] if x["action"] not in ACTIONS else []
            err += [f"{stage}: {x['action']} route {x['route']} != {route(x['action'], c['exposure_usd'])}"] if stage == "final" and x["route"] != route(x["action"], c["exposure_usd"]) else []
            err += [f"{stage}: reason must cite a rule"] if not x["reason"] else []
    final = {x["action"] for x in nba["final"]}
    err += ["sar.file disagrees with FILE_REPORT"] if sar["file"] != ("FILE_REPORT" in final) else []
    if sar["file"]:
        err += ["SAR needs narrative, subjects, amount, dates"] if not (sar["narrative"] and sar["subjects"] and sar["total_amount_usd"] and len(sar["activity_dates"]) == 2) else []
    else:
        err += ["non-filed SAR must be empty"] if sar["narrative"] or sar["subjects"] or sar["total_amount_usd"] or sar["activity_dates"] else []
    err += ["no requests but final != initial"] if not a["evidence_requests"] and nba["final"] != nba["initial"] else []
    err += ["BLOCK_ALL_CARDS used (R10)"] if "BLOCK_ALL_CARDS" in final else []
    return err


def main() -> int:
    st, bad = Store(), 0
    files = sorted(CASES.glob("HHG-*.json"))
    for p in files:
        e = check(json.loads(p.read_text()), st)
        bad += bool(e)
        print(f"{p.stem}: {'ok' if not e else '; '.join(e)}")
    print(f"{len(files) - bad}/{len(files)} valid")
    return 1 if bad or len(files) != 20 else 0


if __name__ == "__main__":
    sys.exit(main())
