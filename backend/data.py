"""Dataset access: raw CSVs -> one cached parquet with card_id and device profile, plus in-memory indexes.

The same `Store` interface is served by TigerGraph (tg.py) when Savanna is configured; the agent only
talks to `store()`, so local and graph runs compute identical evidence.
"""
import os
from functools import cached_property, lru_cache
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")
DATA_DIR = Path(os.environ.get("DATA_DIR", HERE.parent / "data"))
CACHE = HERE / ".cache"

TX_COLS = [
    "TransactionID", "TransactionAmt", "ProductCD", "card4", "card6", "addr1", "addr2", "dist1",
    "P_emaildomain", "R_emaildomain", "M4", "M6", "customer_id", "ts", "channel", "risk_score",
]
ID_COLS = ["TransactionID", "DeviceInfo", "DeviceType", "id_15", "id_23", "id_30", "id_31", "id_33"]


def card_ids(tx: pd.DataFrame) -> pd.Series:
    """card_id = customer_id + '-K' + rank of the customer's (card4, card6) pair, blanks sorted first.

    Reverse-engineered: matches 100% of the 14,955 closed-case transactions and all 20 case-pack cards.
    The sentinel must sort below letters, or blank cards land last and every K shifts.
    """
    key = tx["card4"].fillna("\x00") + "\x01" + tx["card6"].fillna("\x00")
    pairs = pd.DataFrame({"customer_id": tx["customer_id"], "key": key}).drop_duplicates().sort_values(["customer_id", "key"])
    pairs["card_id"] = pairs["customer_id"] + "-K" + (pairs.groupby("customer_id").cumcount() + 1).astype(str)
    return pd.DataFrame({"customer_id": tx["customer_id"], "key": key}).merge(pairs, how="left")["card_id"].values


def device_profile(idt: pd.DataFrame) -> pd.Series:
    """'DeviceInfo | OS | browser | screen', the README's device profile. Blank when there is no DeviceInfo."""
    parts = [idt[c].fillna("unknown").astype(str) for c in ("DeviceInfo", "id_30", "id_31", "id_33")]
    prof = parts[0] + " | " + parts[1] + " | " + parts[2] + " | " + parts[3]
    return prof.where(idt["DeviceInfo"].notna(), "")


def build_cache() -> None:
    CACHE.mkdir(exist_ok=True)
    tx = pd.read_csv(DATA_DIR / "transactions.csv", usecols=TX_COLS, low_memory=False)
    tx["card_id"] = card_ids(tx)
    idt = pd.read_csv(DATA_DIR / "identity.csv", usecols=ID_COLS, low_memory=False)
    idt["device"] = device_profile(idt)
    # Specific = every part known; generic profiles ("Windows | unknown | chrome 66.0 | unknown") sit on hundreds of cards.
    idt["device_specific"] = idt[["DeviceInfo", "id_30", "id_31", "id_33"]].notna().all(axis=1)
    tx = tx.merge(idt[["TransactionID", "device", "device_specific", "DeviceType", "id_15", "id_23"]], on="TransactionID", how="left")
    tx["device"] = tx["device"].fillna("")
    tx["device_specific"] = tx["device_specific"].astype("boolean").fillna(False).astype(bool)
    tx["ts"] = pd.to_datetime(tx["ts"])
    tx.sort_values(["card_id", "ts"]).reset_index(drop=True).to_parquet(CACHE / "tx.parquet")


class Store:
    """In-memory graph view of the dataset. Methods mirror the installed GSQL queries in gsql/queries.gsql."""

    backend = "local"

    @cached_property
    def tx(self) -> pd.DataFrame:
        if not (CACHE / "tx.parquet").exists():
            build_cache()
        return pd.read_parquet(CACHE / "tx.parquet")

    @cached_property
    def _by_card(self) -> dict:
        return self.tx.groupby("card_id").indices

    @cached_property
    def _by_device(self) -> dict:
        d = self.tx[self.tx["device"] != ""]
        return {k: d.index[v] for k, v in d.groupby("device").indices.items()}

    @cached_property
    def closed(self) -> pd.DataFrame:
        cc = pd.read_csv(DATA_DIR / "closed_cases_history.csv", dtype=str, keep_default_na=False)
        cc["exposure_usd"] = cc["exposure_usd"].astype(float)
        return cc

    @cached_property
    def _closed_by_txn(self) -> dict:
        out: dict[int, list[str]] = {}
        for cid, ids in zip(self.closed["case_id"], self.closed["txn_ids"]):
            for t in ids.split("|"):
                if t:
                    out.setdefault(int(t), []).append(cid)
        return out

    @cached_property
    def case_pack(self) -> pd.DataFrame:
        return pd.read_csv(DATA_DIR / "case_pack.csv", dtype={"flagged_txn_id": int})

    # --- graph reads (GSQL: card_txns, device_txns, txn_cases, customer_cards) ---
    def card_txns(self, card_id: str) -> pd.DataFrame:
        return self.tx.iloc[self._by_card.get(card_id, [])]

    def txn(self, txn_id: int) -> pd.Series:
        return self.tx.loc[self.tx["TransactionID"] == txn_id].iloc[0]

    def device_txns(self, device: str, start, end) -> pd.DataFrame:
        idx = self._by_device.get(device)
        if idx is None:
            return self.tx.iloc[[]]
        d = self.tx.loc[idx]
        return d[(d["ts"] >= start) & (d["ts"] <= end)]

    def txn_cases(self, txn_ids) -> list[str]:
        return sorted({c for t in txn_ids for c in self._closed_by_txn.get(int(t), [])})

    def customer_cards(self, customer_id: str) -> list[str]:
        return sorted(c for c in self._by_card if c.startswith(customer_id + "-"))

    def cases_for_cards(self, card_ids) -> pd.DataFrame:
        cc = self.closed
        pattern = "|".join(card_ids)
        return cc[cc["card_id"].isin(card_ids) | cc["connected_card_ids"].str.contains(pattern, regex=True)] if card_ids else cc.iloc[[]]

    def write_case(self, record: dict) -> str | None:
        """Local runs have no graph to write to; the answer file says so (written_to_graph=false)."""
        return None


@lru_cache(maxsize=1)
def store() -> Store:
    from tg import TigerStore, configured  # noqa: PLC0415 - avoid pyTigerGraph import for local runs

    return TigerStore() if configured() else Store()
