"""Learn likelihood ratios from the 5,565 closed cases and check pattern rules against analyst labels.

Writes lr.json (used by agent.py). Run: python calibrate.py
The model risk_score is deliberately left out: cleared cases were alerted at >=0.8 by construction, so its
likelihood ratio here would be a selection artifact, not evidence (README: "a reason to look, never a verdict").
"""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from data import Store
from signals import bins, signals

OUT = Path(__file__).parent / "lr.json"


def classify(s: dict, channel: str) -> str:
    """Pattern rules. Sequence evidence first, then channel-specific typologies from the README."""
    # Loose tiny-charge counts fire on big card buckets; they count only when case memory shows this card was tested before.
    if s["card_testing"] or (channel == "online" and len(s["small_auths"]) >= 2 and s.get("prior_testing")):
        return "card_testing"
    if s["threshold_split"] or len(s["ring_cards"]) >= 2:
        return "undocumented"
    if channel == "online":
        return "card_not_present_new_device" if s["device_new"] else "card_not_present_fraud"
    return "out_of_region_use" if s["away_from_home"] else "account_takeover"


def anchors(store: Store):
    for r in store.closed.itertuples():
        tid = r.first_fraud_txn_id or r.txn_ids.split("|")[0]
        yield r, store.txn(int(tid))


def main() -> None:
    st = Store()
    counts = {"fraud": defaultdict(Counter), "cleared": defaultdict(Counter)}
    pat_ok, pat_n, confusion = 0, 0, Counter()
    n = Counter()
    for r, f in anchors(st):
        s = signals(st, r.card_id, f)
        label = "fraud" if r.outcome == "confirmed_fraud" else "cleared"
        n[label] += 1
        for k, v in bins(s, f["channel"]).items():
            counts[label][k][v] += 1
        if label == "fraud":
            guess = classify(s, f["channel"])
            pat_n += 1
            pat_ok += guess == r.pattern
            confusion[(r.pattern, guess)] += 1

    lr = {}
    for feat in counts["fraud"].keys() | counts["cleared"].keys():
        values = counts["fraud"][feat].keys() | counts["cleared"][feat].keys()
        k = len(values)
        lr[feat] = {
            v: round(((counts["fraud"][feat][v] + 1) / (n["fraud"] + k)) / ((counts["cleared"][feat][v] + 1) / (n["cleared"] + k)), 3)
            for v in sorted(values)
        }
    OUT.write_text(json.dumps({"n": n, "lr": lr, "pattern_accuracy": round(pat_ok / pat_n, 4)}, indent=2))
    print(json.dumps(lr, indent=1))
    print(f"pattern rules: {pat_ok}/{pat_n} = {pat_ok / pat_n:.1%} on confirmed closed cases")
    for (truth, guess), c in sorted(confusion.items(), key=lambda x: -x[1]):
        if truth != guess and c >= 10:
            print(f"  {truth:28} -> {guess:28} {c}")
    assert all(math.isfinite(x) for f in lr.values() for x in f.values())


if __name__ == "__main__":
    main()
