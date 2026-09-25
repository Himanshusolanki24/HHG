"""The investigation agent. One case in, one answer file (README format) + one UI trace out.

Flow (brief §"core investigation flow"): trigger -> graph evidence -> case memory -> score -> policy (initial)
-> controlled evidence request (simulated reply) -> policy (final) -> stop rule -> Mistral writes prose -> case to graph.
Decisions are deterministic: signals.py measures, lr.json (learned from closed cases) weighs, policy.py decides.

Run all 20:  python agent.py            One case:  python agent.py HHG-014
"""
import json
import math
import re
import sys
import time
from pathlib import Path

import pandas as pd

import llm
import policy
from calibrate import classify
from data import store
from signals import bins, signals

HERE = Path(__file__).parent
OUT_CASES = HERE.parent / "cases"  # README: answer files live in cases/ at the repo root
OUT_RUNS = HERE / "runs"  # UI traces
LR = json.loads((HERE / "lr.json").read_text())["lr"]
# Features whose closed-case LRs are not confounded by card-bucket size (recurring / product / small-auth counts are).
USE = ["amount", "device", "region", "match_anomaly", "risk_high"]
TEMPER = 0.6  # naive Bayes over correlated features overcounts; 0.6 keeps closed-case calibration honest
CAP = 8.0
H = pd.Timedelta(hours=1)
# Assumed reply model for controlled evidence requests: (P(signal | fraud), P(signal | legit)).
REQUESTS = {
    "customer_validation": ("Ask the cardholder whether they made the transaction", 0.90, 0.10),
    "step_up_auth": ("Require a one-time passcode before further activity", 0.75, 0.05),
    "analyst_info": ("Ask an analyst for merchant or chargeback context", 0.65, 0.30),
}
PATTERN_NAMES = {
    "card_testing": "card testing", "card_not_present_fraud": "card-not-present fraud",
    "card_not_present_new_device": "card-not-present fraud from a new device", "out_of_region_use": "out-of-region use",
    "account_takeover": "account takeover", "undocumented": "an undocumented pattern", "none": "no fraud pattern",
}


def clean(o):
    """JSON-safe: numpy scalars become Python values (np.bool_ would otherwise serialise as "False"), NaN becomes null."""
    if hasattr(o, "item") and not isinstance(o, (list, dict, str)):
        o = o.item()
    if isinstance(o, float) and math.isnan(o):
        return None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


def dumps(o, **kw):
    return json.dumps(clean(o), allow_nan=False, default=str, **kw)  # default=str only for timestamps


IDS = re.compile(r"\bC\d{5}(?:-K\d)?\b|\bCC-\d{4}\b|\b3\d{6}\b|\$[\d,]+\.\d{2}")
POLICY_REF = re.compile(r"\b(?:policy|rule)\s+[\w.]*\d[\w.]*", re.I)


def grounded(text, facts: dict) -> str:
    """LLM prose is kept only if it is plain text and every ID, amount and policy reference in it appears in the facts."""
    if not isinstance(text, str) or not text.strip():
        return ""
    text = text.replace("**", "").replace("__", "").strip()
    blob = json.dumps(facts, default=str)
    values = {round(float(x.replace(",", "")), 2) for x in re.findall(r"\d[\d,]*\.\d{2}", blob)}  # "$1906.07" == "$1,906.07"
    for tok in IDS.findall(text):
        known = round(float(tok[1:].replace(",", "")), 2) in values if tok.startswith("$") else tok in blob
        if not known:
            print(f"  mistral: rejected text citing {tok}, which is not in the evidence (using template)")
            return ""
    for ref in POLICY_REF.findall(text):
        if not re.search(r"\bR\d+\b|§\s?\d|3a", ref):
            print(f"  mistral: invented policy reference {ref!r} (using template)")
            return ""
    return text


def logit(p): return math.log(p / (1 - p))
def sigmoid(x): return 1 / (1 + math.exp(-x))
def money(x): return f"${x:,.2f}"


def entropy(p):
    return 0.0 if p in (0, 1) else -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def info_gain(p, sens, fpr):
    """Expected reduction in outcome entropy (bits) from a request with this reply model."""
    yes = p * sens + (1 - p) * fpr
    post_yes, post_no = p * sens / yes, p * (1 - sens) / (1 - yes)
    return entropy(p) - (yes * entropy(post_yes) + (1 - yes) * entropy(post_no))


class Trace:
    """Agent steps in the UI's AgentStep shape, timed from when the case was opened."""

    def __init__(self, case_id, opened_at):
        self.case_id, self.t0, self.steps, self.evidence = case_id, pd.Timestamp(opened_at), [], []
        self.clock, self.tokens, self.tool_calls = 0.0, 0, 0

    def step(self, tool, title, inp, summary, *, claims=(), nodes=(), edges=(), evidence=None, rec=None, ms=0.0, tokens=0, wait_s=0.0):
        self.clock += wait_s + max(ms / 1000, 0.4)
        self.tokens += tokens
        self.tool_calls += tool in ("gsql", "graphrag", "policy_lookup")
        if evidence:
            evidence = {"id": f"EV-{self.case_id}-{len(self.evidence) + 1}", **evidence}
            self.evidence.append(evidence)
        self.steps.append({
            "id": f"s{len(self.steps) + 1}", "seq": len(self.steps) + 1,
            "at": (self.t0 + pd.Timedelta(seconds=self.clock)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tool": tool, "title": title, "input": inp, "summary": summary,
            "latencyMs": round(ms if ms else wait_s * 1000), "tokens": {"in": tokens, "out": 0},
            "claims": list(claims), "nodes": list(dict.fromkeys(nodes)), "edges": list(dict.fromkeys(edges)),
            **({"evidence": evidence} if evidence else {}), **({"recommendation": rec} if rec else {}),
        })
        return evidence


def timed(fn, *a):
    t = time.perf_counter()
    out = fn(*a)
    return out, (time.perf_counter() - t) * 1000


# ------------------------------------------------------------------ evidence -> probability
def weigh(s, channel, trigger):
    """Evidence items: (key, likelihood ratio, claim text, entity ids). LRs come from closed cases unless noted."""
    b, items = bins(s, channel), []
    amt_line = f"{s['amount_ratio']:.1f}x the card's median {money(s['median_amt'])}" if not math.isnan(s["amount_ratio"]) else "no prior history on this card"
    text = {
        "amount": f"Amount is {amt_line}",
        "device": {"new_device": "Identity record marks the device New for this account (common in cleared new-phone alerts)",
                   "found_device": "Online purchase from a device the identity record marks Found",
                   "no_identity": "Online purchase with no identity record",
                   "in_person": "Card-present purchase (no device record)"}[b["device"]],
        "region": f"Billing region {s.get('region_label')} is {'away from' if s['away_from_home'] else ''} the card's most-used in-person region {s['home_region']:.0f}".replace("is  the", "is the") if channel != "online" and not math.isnan(s["home_region"]) else "",
        "match_anomaly": "Match flags show a mismatch (M4=M0 or M6=F; unnamed Vesta features)" if s["match_anomaly"] else "Match flags consistent",
        "risk_high": f"Model score {s['risk_score']:.2f} is in the band where most alerts are legitimate (README; cleared closed cases cluster at 0.84-0.92)",
    }
    for k in USE:
        if k == "region" and channel == "online":
            continue
        lr = min(CAP, max(1 / CAP, LR[k].get(b[k], 1.0)))
        if k == "risk_high":
            if trigger != "risk_score":
                continue
            lr = max(0.25, min(1.0, lr))  # a score is a reason to look: it may lower belief, never raise it
        if abs(math.log(lr)) >= math.log(1.5) and text[k]:
            items.append((k, lr, text[k], []))
    if s["recurring_monthly"]:
        items.append(("recurring", 1.0, f"{s['recurring']} earlier charge(s) of the same amount and product code, at roughly monthly intervals", s["recurring_ids"]))
    if s["small_auths"] and not s["card_testing"]:
        items.append(("small_auths", 1.0, f"{len(s['small_auths'])} online authorization(s) under $5 within 72 hours (no R5 sequence)", s["small_auths"]))
    # Sequence and graph evidence: too rare to calibrate per bin, weighted from closed-case outcomes (all confirmed fraud).
    if s["card_testing"]:
        items.append(("card_testing", 20.0, f"R5 shape: {len(s['card_testing']) - 1} online authorizations under $5 within an hour, then a larger purchase", s["card_testing"]))
    if s["threshold_split"]:
        items.append(("threshold_split", 25.0, f"{len(s['threshold_split'])} online purchases between $400 and $500 within an hour, amounts kept under a $500 threshold (as in closed cases CC-3748, CC-3841)", s["threshold_split"]))
    if len(s["ring_cards"]) >= 2:
        lr = 15.0
        items.append(("shared_device", lr, f"Device profile used by {len(s['ring_cards'])} other card(s) within 30 days{' behind an ' + s['proxy'].split(':')[1].lower() + ' proxy' if s['proxy'] else ''}", s["ring_cards"][:12]))
    if s["ring_cases"]:
        items.append(("ring_history", 6.0, f"Same device appears in {len(s['ring_cases'])} closed case(s) on other cards", s["ring_cases"][:6]))
    if trigger == "customer_report":
        if s["recurring_monthly"]:
            items.append(("recurring_dispute", 0.15, f"Disputed amount matches {s['recurring']} earlier charges of the same amount: the customer's own recurring pattern (R7)", s["recurring_ids"]))
        else:
            items.append(("customer_denial", 6.0, "Customer states they did not make the purchase", []))
    return items


def probability(items, prior=0.5):
    """Tempered sum for the correlated closed-case features; direct evidence (sequences, device ring, customer) counts in full."""
    return sigmoid(logit(prior) + sum(math.log(lr) * (TEMPER if k in USE else 1.0) for k, lr, *_ in items))


def interval(p, n):
    """Heuristic 90% band: wider with fewer independent items."""
    sd = 1.6 / math.sqrt(1 + n)
    return sigmoid(logit(p) - 1.645 * sd), sigmoid(logit(p) + 1.645 * sd)


# ------------------------------------------------------------------ episode + memory
def episode(pattern, s, f, card):
    near = card[(card["ts"] - f["ts"]).abs() <= 48 * H]
    if s["threshold_split"]:
        ids = s["threshold_split"]
    elif pattern == "undocumented" and f["device"]:
        ids = card.loc[(card["device"] == f["device"]) & ((card["ts"] - f["ts"]).abs() <= 30 * 24 * H), "TransactionID"].tolist()
    elif pattern == "card_testing":
        ids = s["card_testing"] or [*s["small_auths"], int(f["TransactionID"])]
    elif pattern in ("card_not_present_fraud", "card_not_present_new_device"):
        same_dev = near[(near["channel"] == "online") & (near["device"] == f["device"]) & (f["device"] != "")]
        ids = same_dev["TransactionID"].tolist()
    elif pattern == "out_of_region_use":
        inp = card[(card["ts"] < f["ts"]) & (card["channel"] == "in_person")]
        rare = len(inp) == 0 or (inp["addr1"] == f["addr1"]).mean() < 0.05  # big card buckets use many regions routinely
        day = card[(card["ts"] - f["ts"]).abs() <= 24 * H]
        ids = day.loc[(day["channel"] == "in_person") & (day["addr1"] == f["addr1"]), "TransactionID"].tolist() if rare else []
    else:
        ids = []
    ids = sorted({int(x) for x in [*ids, int(f["TransactionID"])]})
    rows = card[card["TransactionID"].isin(ids)].sort_values("ts")
    return rows


MEMORY: list[dict] = []  # cases closed earlier in this run: the next investigation can find them


def similar_cases(st, card_id, pattern, s, exposure):
    """Case memory retrieval: same card, shared device, then same-typology exemplars (note keyword match)."""
    cc = st.closed
    scored: dict[str, float] = {}
    for cid in cc.loc[cc["card_id"] == card_id, "case_id"]:
        scored[cid] = 0.6
    for cid in s["ring_cases"]:
        scored[cid] = max(scored.get(cid, 0), 0.85)
    key = {"undocumented": "just under \\$500" if s["threshold_split"] else "same device profile",
           "card_testing": "very small online authorizations", "out_of_region_use": "billing region the cardholder had no history",
           "none": "new phone" if s["device_new"] else "travel" if s["away_from_home"] else "unusual for this customer"}.get(pattern)
    pool = cc[cc["pattern"] == pattern] if pattern != "none" else cc[cc["outcome"] == "cleared"]
    if key:
        pool = pool[pool["analyst_notes"].str.contains(key, regex=True)] if pool["analyst_notes"].str.contains(key, regex=True).any() else pool
    if len(pool):
        target = max(exposure, float(s["median_amt"]) if not math.isnan(s["median_amt"]) else 50.0)
        near = pool.assign(d=(pool["exposure_usd"].clip(lower=1) / max(target, 1)).map(lambda r: abs(math.log(r)))).nsmallest(3, "d")
        for cid, d in zip(near["case_id"], near["d"]):
            scored[cid] = max(scored.get(cid, 0), round(0.5 + 0.4 * max(0.0, 1 - d / 3), 2))
    for rec in MEMORY:
        if rec["card_id"] == card_id or set(rec.get("connected", [])) & set(s["ring_cards"]):
            scored[rec["graph_case_id"] or rec["case_id"]] = 0.9
    same_card_bonus = {c: v + (0.25 if c in set(cc.loc[(cc["card_id"] == card_id) & (cc["pattern"] == pattern), "case_id"]) else 0) for c, v in scored.items()}
    top = sorted(same_card_bonus.items(), key=lambda x: -x[1])[:4]
    return [(c, min(0.99, v)) for c, v in top]


# ------------------------------------------------------------------ one case
def investigate(row) -> tuple[dict, dict]:
    st, t_start = store(), time.perf_counter()
    cid, card_id = row["case_id"], row["card_id"]
    tr = Trace(cid, row["opened_at"])
    f, ms = timed(st.txn, int(row["flagged_txn_id"]))
    card, ms2 = timed(st.card_txns, card_id)
    channel = f["channel"]
    ft = f"t:{int(f['TransactionID'])}"
    nodes_base = [f"cust:{row['customer_id']}", f"card:{card_id}", ft]

    tr.step("gsql", "Card history and flagged transaction", f"RUN QUERY card_txns(card_id=\"{card_id}\")",
            f"{len(card)} transactions on {card_id}; flagged {int(f['TransactionID'])} is {money(f['TransactionAmt'])} {channel.replace('_', '-')} "
            f"(product {f['ProductCD']}{', region ' + str(int(f['addr1'])) if pd.notna(f['addr1']) else ''}) at {f['ts']:%Y-%m-%d %H:%M}.",
            claims=[{"text": "Flagged transaction", "ref": {"kind": "node", "id": ft}}], nodes=nodes_base, edges=["e:own", f"e:made:{ft}"], ms=ms + ms2)

    s, ms = timed(signals, st, card_id, f)
    s["region_label"] = f"{f['addr1']:.0f}" if pd.notna(f["addr1"]) else "unknown"
    items = weigh(s, channel, row["trigger_type"])

    win_nodes = [f"t:{t}" for t in s["card_testing"] + s["threshold_split"] + s["small_auths"][:6]]
    tr.step("gsql", "Behaviour around the alert", f"RUN QUERY card_window(card_id=\"{card_id}\", center={int(f['TransactionID'])}, hours=48)",
            f"{s['burst_online_48h']} online transaction(s) within 48 hours; {s['recurring']} earlier charge(s) of the same amount; "
            f"{'card-testing sequence found' if s['card_testing'] else 'no R5 card-testing sequence'}; "
            f"{'sub-$500 split found' if s['threshold_split'] else 'no sub-$500 split'}.",
            claims=[{"text": t, "ref": {"kind": "node", "id": f"t:{ids[0]}" if ids and isinstance(ids[0], int) else ft}} for k, _, t, ids in items if k in ("recurring", "small_auths_72h", "card_testing", "threshold_split", "amount")],
            nodes=[*nodes_base, *win_nodes], edges=[f"e:made:t:{t}" for t in s["card_testing"] + s["threshold_split"]], ms=ms,
            evidence={"kind": "graph", "label": "Card behaviour", "summary": "; ".join(t for k, _, t, _ in items if k not in ("shared_device", "ring_history", "customer_denial", "recurring_dispute"))[:300],
                      "source": f"GSQL card_window @ {st.backend}", "nodes": [ft, *win_nodes]})

    dev_nodes = []
    if f["device"]:
        dev = f"d:{f['device']}"
        dev_nodes = [dev, *[f"card:{c}" for c in s["ring_cards"][:12]]]
        tr.step("gsql", "Device and its other cards", f"RUN QUERY device_txns(device=\"{f['device']}\", days=30)",
                f"Device {f['device']} ({f.get('id_15') or 'no New/Found flag'}{', proxy ' + s['proxy'] if s['proxy'] else ''}) "
                f"{'is used by ' + str(len(s['ring_cards'])) + ' other card(s) within 30 days' if s['ring_cards'] else 'is not shared with other cards (or is too generic to count)'}"
                f"{'; ' + str(len(s['ring_cases'])) + ' closed case(s) involve it' if s['ring_cases'] else ''}.",
                claims=[{"text": t, "ref": {"kind": "node", "id": dev}} for k, _, t, _ in items if k in ("shared_device", "ring_history", "device")],
                nodes=[ft, *dev_nodes], edges=[f"e:dev:{ft}", *[f"e:ring:{c}" for c in s["ring_cards"][:12]]],
                evidence={"kind": "graph", "label": "Shared device" if s["ring_cards"] else "Device", "summary": f"{len(s['ring_cards'])} other cards on {f['device']}",
                          "source": f"GSQL device_txns @ {st.backend}", "nodes": dev_nodes[:6]} if s["ring_cards"] else None)

    p0 = probability(items)
    lean_fraud = p0 >= 0.5
    candidate = classify(s, channel)  # what it would be if it is fraud; applied when the belief says so
    pattern = candidate if lean_fraud else "none"
    ep = episode(candidate, s, f, card) if lean_fraud else card.iloc[[]]
    exposure = round(float(ep["TransactionAmt"].abs().sum()), 2)

    sim = similar_cases(st, card_id, pattern, s, exposure)
    notes = st.closed.set_index("case_id")["analyst_notes"].to_dict()
    tr.step("graphrag", "Retrieve similar closed cases", f"graphrag.retrieve(card={card_id}, pattern={pattern}, device_ring={bool(s['ring_cards'])}, k=4)",
            f"{len(sim)} prior case(s): " + ", ".join(f"{c} ({v:.2f})" for c, v in sim) + ".",
            claims=[{"text": f"{c}: {notes.get(c, 'case from this run')[:90]}...", "ref": {"kind": "node", "id": f"cc:{c}"}} for c, _ in sim[:3]],
            nodes=[f"cc:{c}" for c, _ in sim], edges=[f"e:cc:{c}" for c, _ in sim], ms=40,
            evidence={"kind": "retrieval", "label": "Case memory", "summary": f"{len(sim)} similar closed cases", "source": "closed_cases_history + this run's cases", "nodes": [f"cc:{c}" for c, _ in sim]})

    sup = [i for i in items if i[1] != 1.0 and (i[1] > 1) == lean_fraud]
    conflicting = any(lr >= 4 for _, lr, *_ in items) and any(lr <= 0.25 for _, lr, *_ in items)
    shared = f"device profile {f['device']} behind {s['proxy']}" if len(s["ring_cards"]) >= 2 else ""
    sit = policy.Situation(
        trigger=row["trigger_type"], p=p0, n_evidence=len(sup), pattern=pattern, exposure=exposure,
        recurring_dispute=row["trigger_type"] == "customer_report" and s["recurring_monthly"] and not (s["threshold_split"] or shared),
        shared_origin=shared, undocumented=pattern == "undocumented", card_testing=bool(s["card_testing"]),
        cleared_over_100=any(card.loc[card["TransactionID"].isin(s["card_testing"]), "TransactionAmt"] > 100),
        connected_cards=s["ring_cards"] if shared else [], conflicting=conflicting,
    )
    tr.step("policy_lookup", "Apply fraud policy", f"policy.recommend(p={p0:.2f}, evidence={len(sup)}, pattern={pattern}, exposure={exposure})",
            f"Rules in play: {', '.join(sorted({a['reason'].split(':')[0] for a in policy.recommend(sit)}))}.",
            claims=[{"text": policy.RULES[r][:110], "ref": {"kind": "policy", "id": r}} for r in sorted({a["reason"].split(":")[0] for a in policy.recommend(sit)}) if r in policy.RULES], ms=2)

    def rec(stage, sit_, p_, items_, caused):
        lo, hi = interval(p_, len(items_))
        verdict = "fraud" if p_ >= 0.7 else "legitimate" if p_ <= 0.3 else "uncertain"
        return {
            "id": f"R-{cid}-{stage}", "stage": stage, "verdict": verdict, "pattern": pattern if verdict != "legitimate" else "none",
            "p": round(p_, 3), "pLo": round(lo, 3), "pHi": round(hi, 3), "actions": policy.recommend(sit_),
            "unknowns": [{"id": k, "question": q, "infoGain": round(info_gain(p_, se, fp), 3), "resolved": stage == "final" and k == req}
                         for k, (q, se, fp) in REQUESTS.items()],
            "causedBy": caused,
        }

    initial = rec("initial", sit, p0, items, [e["id"] for e in tr.evidence])
    tr.step("recommend", "Initial recommendation", f"reason(evidence={len(items)} items, prior=0.50)",
            f"Fraud probability {p0:.2f} ({initial['verdict']}): " + ", ".join(a["action"] for a in initial["actions"]) + ".",
            claims=[{"text": a["reason"], "ref": {"kind": "policy", "id": a["reason"].split(":")[0]}} for a in initial["actions"][:3]], rec=initial)

    req = policy.needs_evidence(sit)
    requests, final, p1 = [], initial, p0
    if req:
        q, sens, fpr = REQUESTS[req]
        response = "confirmed" if sit.recurring_dispute or p0 < 0.5 else "denied"
        assumed = {
            ("customer_validation", "denied"): "Customer states they did not make the purchase and still holds the card",
            ("customer_validation", "confirmed"): "Customer recognises the charge" + (" as their recurring payment" if sit.recurring_dispute else " (for example a new phone or a planned purchase)"),
        }[(req, response)]
        requests.append({"type": req, "asked_after_step": len(tr.steps), "assumed_response": f"{assumed}. Simulated: replies are not provided in this round; assumption follows the graph evidence (probability {p0:.2f})."})
        tr.step("evidence_request", "Ask the cardholder", f"evidence.request({req}, card={card_id})",
                f"{q}. Expected information gain {info_gain(p0, sens, fpr):.2f} bits, the highest of the permitted requests. Case waits for the reply.",
                claims=[{"text": policy.RULES['R1' if not sit.recurring_dispute else 'R7'][:110], "ref": {"kind": "policy", "id": "R1" if not sit.recurring_dispute else "R7"}}])
        lr_reply = sens / fpr if response == "denied" else (1 - sens) / (1 - fpr)
        items = [*items, (req, lr_reply, assumed, [])]
        p1 = sigmoid(logit(p0) + math.log(lr_reply))
        ev = tr.step("evidence_response", "Cardholder replied (simulated)", f"evidence.response({req})", assumed + ".",
                     claims=[{"text": assumed, "ref": {"kind": "node", "id": f"cust:{row['customer_id']}"}}], nodes=[f"cust:{row['customer_id']}"],
                     evidence={"kind": "external", "label": "Customer reply", "summary": assumed, "source": f"evidence_request:1 ({req}, simulated)", "nodes": [f"cust:{row['customer_id']}"]},
                     wait_s=3600 * 2)
        sit.response, sit.p, sit.n_evidence = response, p1, sit.n_evidence + 1
        if response == "confirmed":
            pattern, exposure, ep = "none", 0.0, card.iloc[[]]
        else:
            pattern, ep = candidate, episode(candidate, s, f, card)
            exposure = round(float(ep["TransactionAmt"].abs().sum()), 2)
        sit.pattern, sit.exposure = pattern, exposure
        final = rec("final", sit, p1, items, [ev["id"]])
        tr.step("recommend", "Recommendation after the reply", f"reason(prior=R-{cid}-initial, reply={response})",
                f"Probability {p0:.2f} -> {p1:.2f}: " + ", ".join(a["action"] for a in final["actions"]) + ".",
                claims=[{"text": a["reason"], "ref": {"kind": "policy", "id": a["reason"].split(":")[0]}} for a in final["actions"][:3]], rec=final)

    verdict = final["verdict"]
    final_actions = [a["action"] for a in final["actions"]]
    filing = "FILE_REPORT" in final_actions
    status = "escalated" if "ESCALATE_TO_ANALYST" in final_actions else "closed_fraud" if verdict == "fraud" else "closed_legitimate" if verdict == "legitimate" else "open"
    affected = [str(int(x)) for x in ep["TransactionID"]] if verdict != "legitimate" else []
    exposure = round(float(ep["TransactionAmt"].abs().sum()), 2) if affected else 0.0
    connected = s["ring_cards"] if shared else []
    devices = [f["device"]] if shared else []
    evidence = [{"claim": t, "source": "customer" if k in REQUESTS or k == "customer_denial" else "graph",
                 "ref": f"evidence_request:1" if k in REQUESTS else "trigger:customer_report" if k in ("customer_denial", "recurring_dispute") else f"query:{'device_txns' if k in ('shared_device', 'ring_history') else 'card_window'}(card_id={card_id})",
                 "entity_ids": [str(x) for x in ids] or [str(int(f["TransactionID"]))]} for k, lr, t, ids in items]
    evidence.append({"claim": f"Model risk score {f['risk_score']:.2f} treated as a reason to look, not evidence: in closed cases, cleared alerts cluster at 0.84-0.92",
                     "source": "document", "ref": "README §0; closed_cases_history", "entity_ids": [str(int(f["TransactionID"]))]})
    if sim:
        evidence.append({"claim": "Similar closed cases: " + "; ".join(f"{c}: {notes.get(c, '')[:80]}" for c, _ in sim[:2]), "source": "graph", "ref": "graphrag.retrieve(case_memory)", "entity_ids": [c for c, _ in sim]})

    # --- prose: Mistral writes from facts only; templates keep the run reproducible without a key
    facts = {
        "case_id": cid, "trigger": row["trigger_text"], "verdict": verdict, "fraud_probability": round(p1, 2), "pattern": PATTERN_NAMES[pattern if verdict != "legitimate" else "none"],
        "evidence": [e["claim"] for e in evidence], "initial_actions": [a["action"] for a in initial["actions"]], "final_actions": final_actions,
        "evidence_request": requests, "affected_txn_ids": affected, "exposure_usd": exposure, "connected_cards": connected[:12], "device": devices,
        "customer_id": row["customer_id"], "card_id": card_id, "dates": [ep["ts"].min().strftime("%Y-%m-%d"), ep["ts"].max().strftime("%Y-%m-%d")] if affected else [],
        "similar_cases": {c: notes.get(c, "")[:200] for c, _ in sim[:3]}, "file_report": filing,
    }
    system = ("You write for a bank fraud team. Use ONLY the facts given: never invent IDs, amounts, dates, counts, policy numbers, attack types or motives. "
        "Every value must be ONE plain-text string: no markdown, no bullet points, no nested objects. Return JSON with exactly these keys: "
        '{"summary": "2-6 sentences for an analyst", '
        '"sar_narrative": "one paragraph of 6-12 sentences stating who, what, when, where, how and why it is suspicious; empty string if file_report is false", '
        '"pattern_description": "2-3 sentences on what the pattern is, who it affects and how it was found, if pattern is an undocumented pattern; else empty string"}')
    need = ["summary", *(["sar_narrative"] if filing else []), *(["pattern_description"] if pattern == "undocumented" else [])]
    prose, tok = {}, 0
    for _ in range(2):  # one retry: a field that cites anything outside the evidence is rejected and re-asked
        got, t = llm.write_json(system, facts)
        tok += t
        for k, v in (got or {}).items():
            if k in need and k not in prose and (ok := grounded(v, facts)):
                prose[k] = ok
        if not got or all(k in prose for k in need):
            break
    tr.tokens += tok
    summary = prose.get("summary") or (
        f"{row['trigger_type'].replace('_', ' ').capitalize()} on {card_id}: flagged {money(f['TransactionAmt'])} {channel.replace('_', '-')} transaction {int(f['TransactionID'])}. "
        f"Verdict {verdict} at probability {p1:.2f}, pattern {PATTERN_NAMES[pattern if verdict != 'legitimate' else 'none']}. "
        + (f"Episode of {len(affected)} transaction(s), exposure {money(exposure)}. " if affected else "")
        + f"Strongest evidence: {max(items, key=lambda i: abs(math.log(i[1])))[2]}.")
    what_changed = ("nothing" if not requests else
        f"The assumed reply ({requests[0]['assumed_response'].split('.')[0].lower()}) moved probability from {p0:.2f} to {p1:.2f}, "
        f"changing the actions from {', '.join(initial_actions := [a['action'] for a in initial['actions']])} to {', '.join(final_actions)}.")
    stop = (
        f"Probability {p1:.2f} with {sit.n_evidence} independent item(s): " + ("the verification reply settles it (policy §6)." if requests else "past the 0.85/0.15 threshold with two independent items (policy §6)."))
    pattern_desc = (prose.get("pattern_description") or (
        f"Several online purchases just under $500 inside an hour on {card_id}, apparently sized to stay below a $500 authorization threshold; the model scored them low. Found by scanning the card's 24-hour window; matches closed cases CC-3748 and CC-3841."
        if s["threshold_split"] else
        f"One device profile ({f['device']}) behind an anonymising proxy made purchases on {len(s['ring_cards']) + 1} unrelated cards within 30 days. Found by traversing the flagged transaction's device to its other cards; mirrors closed undocumented cases CC-2649 and CC-2971.")
    ) if pattern == "undocumented" and verdict != "legitimate" else ""
    narrative = prose.get("sar_narrative") if filing else ""
    if filing and not narrative:
        narrative = (f"Between {facts['dates'][0]} and {facts['dates'][1]}, card {card_id} belonging to customer {row['customer_id']} was used for {len(affected)} "
                     f"{channel.replace('_', '-')} transaction(s) totalling {money(exposure)} ({', '.join(affected[:8])}). "
                     + " ".join(e["claim"] + "." for e in evidence[:4])
                     + f" The activity is consistent with {PATTERN_NAMES[pattern]}. Recommended actions: {', '.join(final_actions)}.")

    answer = {
        "case_id": cid,
        "case": {
            "status": status, "verdict": verdict, "fraud_probability": round(p1, 2),
            "pattern": pattern if verdict != "legitimate" else "none", "pattern_description": pattern_desc,
            "affected_txn_ids": affected, "first_suspicious_txn_id": affected[0] if affected else "",
            "connected_card_ids": connected, "connected_device_profiles": devices, "exposure_usd": exposure,
            "evidence": evidence, "similar_prior_cases": [c for c, _ in sim if c.startswith("CC-")],
            "summary": summary, "written_to_graph": False, "graph_case_id": "",
        },
        "evidence_requests": requests,
        "next_best_actions": {"initial": initial["actions"], "final": final["actions"], "what_changed": what_changed},
        "sar": {"file": filing, "reason": next((a["reason"] for a in final["actions"] if a["action"] == "FILE_REPORT"),
                                               "No report: verdict is legitimate; policy 3a files only for confirmed or strongly suspected fraud." if verdict == "legitimate" else
                                               f"No report: policy 3a thresholds not met (exposure {money(exposure)} is under $1,000, no shared device, region cluster or coordinated pattern)."),
                "narrative": narrative, "subjects": ([row["customer_id"], card_id, *connected[:12], *devices] if filing else []),
                "total_amount_usd": exposure if filing else 0, "activity_dates": facts["dates"] if filing else []},
        "stop_reason": stop,
        "tool_calls": tr.tool_calls, "tokens": tr.tokens, "latency_s": 0.0,
    }

    gid = st.write_case({"case_id": cid, "answer": answer, "card_id": card_id, "affected": affected, "connected": connected, "similar": answer["case"]["similar_prior_cases"], "device": devices})
    answer["case"]["written_to_graph"], answer["case"]["graph_case_id"] = bool(gid), gid or ""
    tr.step("gsql", "Write case to graph" if gid else "Record case in memory", f"UPSERT InvestigationCase(\"{gid or cid}\")",
            f"{'Written to TigerGraph as ' + gid if gid else 'TigerGraph not configured: kept in local case memory for later investigations'}; status {status}.", ms=5)
    MEMORY.append({"case_id": cid, "graph_case_id": gid, "card_id": card_id, "connected": connected})
    answer["tool_calls"] = tr.tool_calls
    answer["latency_s"] = round(time.perf_counter() - t_start, 2)
    return answer, ui_run(row, f, card, s, ep, sim, notes, tr, answer)


# ------------------------------------------------------------------ UI trace
def ui_run(row, f, card, s, ep, sim, notes, tr, answer):
    ft, card_node = f"t:{int(f['TransactionID'])}", f"card:{row['card_id']}"
    p = answer["case"]["fraud_probability"]
    affected = set(answer["case"]["affected_txn_ids"])
    near = card[(card["ts"] - f["ts"]).abs() <= 72 * H]
    show = pd.concat([ep, near.iloc[(near["ts"] - f["ts"]).abs().argsort()[:10]], card[card["TransactionID"].isin(s["recurring_ids"][-3:] + s["small_auths"][:4])]]).drop_duplicates("TransactionID")
    nodes = {f"cust:{row['customer_id']}": {"type": "customer", "label": row["customer_id"], "risk": 0.05, "attrs": {"cards": len(store().customer_cards(row["customer_id"]))}},
             card_node: {"type": "card", "label": row["card_id"], "risk": p, "attrs": {"transactions": len(card), "median_amount": money(s["median_amt"]) if not math.isnan(s["median_amt"]) else "n/a"}}}
    edges = {"e:own": (f"cust:{row['customer_id']}", card_node, "OWNS", 1)}
    for r in show.itertuples():
        tid = f"t:{int(r.TransactionID)}"
        nodes[tid] = {"type": "transaction", "label": f"{money(r.TransactionAmt)} {r.ProductCD}", "risk": 0.9 if str(int(r.TransactionID)) in affected else float(r.risk_score) * 0.5,
                      "attrs": {"id": int(r.TransactionID), "at": f"{r.ts:%Y-%m-%d %H:%M}", "channel": r.channel, "product": r.ProductCD, "region": "" if pd.isna(r.addr1) else int(r.addr1), "model_score": r.risk_score}}
        edges[f"e:made:{tid}"] = (card_node, tid, "MADE", round(r.TransactionAmt, 2))
        if r.device:
            d = f"d:{r.device}"
            nodes.setdefault(d, {"type": "device", "label": r.device.split(" | ")[0][:28], "risk": 0.9 if len(s["ring_cards"]) >= 2 and s["proxy"] and r.device == f["device"] else 0.3 if r.id_15 == "New" else 0.1,
                                 "attrs": {"profile": r.device, "flag": r.id_15 if isinstance(r.id_15, str) else "", "proxy": r.id_23 if isinstance(r.id_23, str) else "none"}})
            edges[f"e:dev:{tid}"] = (tid, d, "FROM_DEVICE", 1)
        elif pd.notna(r.addr1):
            rg = f"r:{int(r.addr1)}"
            nodes.setdefault(rg, {"type": "region", "label": f"Region {int(r.addr1)}", "risk": 0.1 if r.addr1 == s["home_region"] else 0.5, "attrs": {"home_region": r.addr1 == s["home_region"]}})
            edges[f"e:reg:{tid}"] = (tid, rg, "BILLED_IN", 1)
        if pd.notna(r.P_emaildomain):
            em = f"m:{r.P_emaildomain}"
            nodes.setdefault(em, {"type": "email", "label": r.P_emaildomain, "risk": 0.05, "attrs": {}})
            edges.setdefault(f"e:mail:{r.P_emaildomain}", (tid, em, "PURCHASER_EMAIL", 1))
    if f["device"]:
        for c in s["ring_cards"][:12]:
            nodes[f"card:{c}"] = {"type": "card", "label": c, "risk": 0.7, "attrs": {"link": "shares device profile"}}
            edges[f"e:ring:{c}"] = (f"d:{f['device']}", f"card:{c}", "USED_ON", 1)
    cc_outcome = store().closed.set_index("case_id")["outcome"].to_dict()
    for c, v in sim:
        outcome = cc_outcome.get(c, "")
        nodes[f"cc:{c}"] = {"type": "prior_case", "label": c, "risk": 0.9 if outcome == "confirmed_fraud" else 0.1,
                            "attrs": {"similarity": v, "note": notes.get(c, "")[:160]}}
        edges[f"e:cc:{c}"] = (f"cc:{c}", card_node, "SIMILAR_TO", v)
    cc = store().closed.set_index("case_id")
    return {
        "caseId": row["case_id"], "subjectId": card_node, "alertAt": f"{f['ts']:%Y-%m-%dT%H:%M:%SZ}",
        "nodes": [{"id": k, **v} for k, v in nodes.items()],
        "edges": [{"id": k, "source": a, "target": b, "rel": rel, "weight": w} for k, (a, b, rel, w) in edges.items() if a in nodes and b in nodes],
        "transactions": [{"id": str(int(r.TransactionID)), "at": f"{r.ts:%Y-%m-%dT%H:%M:%SZ}", "amount": round(r.TransactionAmt, 2),
                          "merchant": f"Product {r.ProductCD}, {r.channel.replace('_', '-')}" + (f", region {int(r.addr1)}" if pd.notna(r.addr1) else ""),
                          "direction": "out", "flagged": str(int(r.TransactionID)) in affected or r.TransactionID == f["TransactionID"]}
                         for r in card[(card["ts"] - f["ts"]).abs() <= 7 * 24 * H].itertuples()],
        "similar": [{"caseId": c, "similarity": v, "outcome": cc.loc[c, "outcome"].replace("cleared", "false_positive") if c in cc.index else "inconclusive",
                     "decision": cc.loc[c, "actions_taken"].replace("|", ", ") if c in cc.index else "Investigated earlier in this run",
                     "analystNote": cc.loc[c, "analyst_notes"] if c in cc.index else ""} for c, v in sim],
        "steps": tr.steps,
        "answer": answer,
    }


QUEUE_STATUS = {"closed_legitimate": "closed", "closed_fraud": "ready_to_act", "escalated": "ready_to_act", "open": "open"}


def queue_row(row, answer=None):
    """Case-queue entry for the UI. Before a run the queue only knows the case pack."""
    import re  # noqa: PLC0415
    m = re.search(r"\$([\d,]+\.\d{2})", row["trigger_text"])
    amt = m.group(1) if m else ""
    title = {"risk_score": f"Model alert on ${amt} {'in-person' if 'region' in row['trigger_text'] else 'online'} purchase",
             "customer_report": f"Customer disputes ${amt} charge", "analyst_request": "Analyst: shared unusual device profile"}[row["trigger_type"]]
    c = answer["case"] if answer else None
    rec = next((x for x in answer["next_best_actions"]["final"]), None) if answer else None
    return {
        "id": row["case_id"], "title": title, "trigger": row["trigger_type"], "pattern": c["pattern"] if c else "none",
        "status": QUEUE_STATUS[c["status"]] if c else "open", "risk": c["fraud_probability"] if c else 0.5,
        "confidence": round(1 - (answer["_band"][1] - answer["_band"][0]), 2) if c else 0.0, "modelScore": None if pd.isna(row["risk_score"]) else float(row["risk_score"]),
        "stateSince": pd.Timestamp(row["opened_at"]).strftime("%Y-%m-%dT%H:%M:%SZ"), "hasRun": bool(c), "cardId": row["card_id"], "firstAction": rec["action"] if rec else "",
    }


def export_policies():
    return [{"id": k, "doc": "Fraud Policy v1.0", "clause": k if k[0] == "R" else f"§{k}", "title": v.split(":")[0], "text": v} for k, v in policy.RULES.items()]


def main(ids):
    OUT_CASES.mkdir(exist_ok=True)
    OUT_RUNS.mkdir(exist_ok=True)
    cp = store().case_pack
    rows = cp[cp["case_id"].isin(ids)] if ids else cp
    queue = {}
    for row in rows.sort_values("opened_at").to_dict("records"):  # chronological, so memory flows forward
        answer, run = investigate(row)
        (OUT_CASES / f"{row['case_id']}.json").write_text(dumps(answer, indent=2))
        (OUT_RUNS / f"{row['case_id']}.json").write_text(dumps(run))
        final = run["steps"][[i for i, st in enumerate(run["steps"]) if "recommendation" in st][-1]]["recommendation"]
        queue[row["case_id"]] = queue_row(row, {**answer, "_band": (final["pLo"], final["pHi"])})
        c = answer["case"]
        print(f"{row['case_id']} {c['verdict']:10} p={c['fraud_probability']:.2f} {c['pattern']:28} ${c['exposure_usd']:>9,.2f} "
              f"final={[a['action'] for a in answer['next_best_actions']['final']]}")
    if not ids:
        (OUT_RUNS / "queue.json").write_text(dumps([queue[r] for r in cp["case_id"]], indent=1))
        (OUT_RUNS / "policies.json").write_text(json.dumps(export_policies(), indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
