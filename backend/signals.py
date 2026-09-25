"""Evidence signals for one transaction on one card. Shared by calibrate.py (closed cases) and agent.py (exam cases)."""
import math

import pandas as pd

H = pd.Timedelta(hours=1)
PROXY_BAD = {"IP_PROXY:ANONYMOUS", "IP_PROXY:HIDDEN"}


def _card_testing(win: pd.DataFrame) -> list[int]:
    """R5 shape: 3+ online authorizations under $5 within an hour, then a larger online purchase."""
    online = win[win["channel"] == "online"]
    small = online[online["TransactionAmt"] < 5]
    for _, big in online[online["TransactionAmt"] >= 10].iterrows():
        probes = small[(small["ts"] >= big["ts"] - H) & (small["ts"] < big["ts"])]
        if len(probes) >= 3:
            return [*probes["TransactionID"].astype(int), int(big["TransactionID"])]
    return []


def _threshold_split(win: pd.DataFrame, lo=400, hi=500) -> list[int]:
    """Undocumented pattern seen in closed cases CC-3748 et al.: 3+ online purchases just under $500 within an hour."""
    d = win[(win["channel"] == "online") & win["TransactionAmt"].between(lo, hi, inclusive="left")]
    for t0 in d["ts"]:
        grp = d[(d["ts"] >= t0) & (d["ts"] <= t0 + H)]
        if len(grp) >= 3:
            return grp["TransactionID"].astype(int).tolist()
    return []


def signals(store, card_id: str, f: pd.Series) -> dict:
    card = store.card_txns(card_id)
    hist = card[card["ts"] < f["ts"]]
    win = card[(card["ts"] >= f["ts"] - 48 * H) & (card["ts"] <= f["ts"] + 48 * H)]
    amt = float(f["TransactionAmt"])
    med = float(hist["TransactionAmt"].median()) if len(hist) else math.nan
    online = f["channel"] == "online"

    home = hist.loc[hist["channel"] == "in_person", "addr1"].mode()
    home = float(home.iloc[0]) if len(home) else math.nan
    near = card[(card["ts"] - f["ts"]).abs() <= 24 * H]
    home_active = bool(((near["addr1"] == home) & (near["channel"] == "in_person") & (near["TransactionID"] != f["TransactionID"])).any())

    same_amt = hist[((hist["TransactionAmt"] - amt).abs() <= max(0.5, 0.01 * amt)) & (hist["ProductCD"] == f["ProductCD"])]
    # R7 "same merchant, same amount, monthly": at least two ~monthly gaps. A raw count would fire on every big card bucket.
    # Last two gaps (including the one up to this charge) must both be ~monthly; big card buckets match amounts by chance otherwise.
    chain = [*same_amt["ts"].tail(2), f["ts"]]
    monthly = len(chain) == 3 and all(26 <= (b - a).days <= 35 for a, b in zip(chain, chain[1:]))

    online_win72 = card[((card["ts"] - f["ts"]).abs() <= 72 * H) & (card["channel"] == "online")]
    prior_cases = store.closed[(store.closed["card_id"] == card_id) & (store.closed["opened_at"] < str(f["ts"]))]

    s = {
        "n_hist": len(hist),
        "median_amt": med,
        "amount_ratio": amt / med if med and med > 0 else math.nan,
        "product_new": bool(len(hist)) and f["ProductCD"] not in set(hist["ProductCD"]),
        "region_seen": int((hist["addr1"] == f["addr1"]).sum()) if pd.notna(f["addr1"]) else -1,
        "home_region": home,
        # Labels say out-of-region = away from the card's most-used in-person region (95% vs 21% for takeover).
        "away_from_home": bool(pd.notna(f["addr1"]) and pd.notna(home) and f["addr1"] != home),
        "home_active": home_active,
        # Identity record's own flag. "Not in this card's history" does not separate the labels (cards are shared buckets).
        "device_new": bool(online and f.get("id_15") == "New"),
        "proxy": f.get("id_23") if f.get("id_23") in PROXY_BAD else "",
        "recurring": len(same_amt),
        "recurring_monthly": bool(monthly),
        "recurring_ids": same_amt["TransactionID"].astype(int).tolist()[-6:],
        "burst_online_48h": int((win["channel"] == "online").sum()),
        "match_anomaly": f.get("M4") == "M0" or f.get("M6") == "F",
        "card_testing": _card_testing(win),  # strict R5 shape
        "small_auths": online_win72.loc[online_win72["TransactionAmt"] < 5, "TransactionID"].astype(int).tolist(),
        "prior_fraud_cases": prior_cases.loc[prior_cases["outcome"] == "confirmed_fraud", "case_id"].tolist(),
        "prior_cleared_cases": prior_cases.loc[prior_cases["outcome"] == "cleared", "case_id"].tolist(),
        "prior_testing": prior_cases.loc[prior_cases["pattern"] == "card_testing", "case_id"].tolist(),
        "threshold_split": _threshold_split(card[(card["ts"] - f["ts"]).abs() <= 24 * H]),
        "ring_cards": [],
        "ring_cases": [],
        "risk_score": float(f["risk_score"]),
        "has_identity": bool(online and pd.notna(f.get("id_15"))),
    }
    # Shared device: only specific profiles count; generic ones ("Windows | chrome 66") sit on hundreds of cards.
    # Ring = a specific profile that only ever appears behind this proxy type (the SM-G935F ring: 100% of 52 cards).
    # Popular profiles (Windows 10 / Chrome 65: proxy on 3 of 299 cards) are ordinary shared hardware, not a ring.
    if online and f["device"] and f["device_specific"] and s["proxy"]:
        allrows = store.device_txns(f["device"], pd.Timestamp.min, pd.Timestamp.max)
        s["proxy_share"] = round(float((allrows["id_23"] == f["id_23"]).mean()), 2) if len(allrows) else 0.0
        nb = store.device_txns(f["device"], f["ts"] - 30 * 24 * H, f["ts"] + 30 * 24 * H)
        others = nb[(nb["card_id"] != card_id) & (nb["id_23"] == f["id_23"])] if s["proxy_share"] >= 0.8 else nb.iloc[[]]
        s["ring_cards"] = sorted(others["card_id"].unique().tolist())
        s["ring_txns"] = others["TransactionID"].astype(int).tolist()
        s["ring_cases"] = store.txn_cases(s["ring_txns"])
    return s


# --- discretisation used by calibration and scoring (one place, so they can't drift) ---
def bins(s: dict, channel: str) -> dict:
    r = s["amount_ratio"]
    return {
        "amount": "no_history" if math.isnan(r) else "<0.5x" if r < 0.5 else "0.5-2x" if r < 2 else "2-5x" if r < 5 else ">=5x",
        "device": "in_person" if channel != "online" else "no_identity" if not s["has_identity"] else "new_device" if s["device_new"] else "found_device",
        "region": "online" if channel == "online" else "away_from_home" if s["away_from_home"] else "home_region",
        "recurring_monthly": str(s["recurring_monthly"]),
        # README: "Above 0.7, most flagged transactions turn out to be legitimate." Only ever used to lower probability.
        "risk_high": str(s["risk_score"] >= 0.8),
        "match_anomaly": str(bool(s["match_anomaly"])),
    }
