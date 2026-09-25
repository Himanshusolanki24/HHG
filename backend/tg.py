"""TigerGraph Savanna backend: same Store interface, graph reads via installed GSQL queries, cases written as vertices.

Setup once:  python tg.py setup   (schema + bulk load + install queries; see gsql/)
"""
import json
import os
import socket
import sys
from functools import cached_property
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from data import CACHE, TX_COLS, Store

COLUMNS = [*TX_COLS, "card_id", "device", "device_specific", "DeviceType", "id_15", "id_23"]

GSQL = Path(__file__).parent / "gsql"


def configured() -> bool:
    host = urlparse(os.environ.get("SAVANNA_HOST", "")).hostname
    if not host:
        return False
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        print(f"SAVANNA_HOST {host} does not resolve; running on local data.", file=sys.stderr)
        return False
    # A resolvable host can still be a stopped workspace; only use the graph when it answers.
    import httpx  # noqa: PLC0415

    try:
        r = httpx.get(os.environ["SAVANNA_HOST"].rstrip("/") + "/api/ping", timeout=15)
    except httpx.HTTPError as e:
        print(f"Savanna unreachable ({e}); running on local data.", file=sys.stderr)
        return False
    if r.status_code != 200:
        print(f"Savanna not ready ({r.status_code}: {r.text.strip()[:120]}); running on local data.", file=sys.stderr)
        return False
    return True


def connect():
    import pyTigerGraph as tg  # noqa: PLC0415

    login = {k: os.environ[e] for k, e in (("username", "SAVANNA_USERNAME"), ("password", "SAVANNA_PASSWORD")) if os.environ.get(e)}
    conn = tg.TigerGraphConnection(
        host=os.environ["SAVANNA_HOST"], graphname=os.environ.get("SAVANNA_GRAPH", "FraudGraph"),
        gsqlSecret=os.environ.get("SAVANNA_SECRET") or "", tgCloud=True, **login,
    )
    if os.environ.get("SAVANNA_SECRET"):
        conn.getToken(os.environ["SAVANNA_SECRET"])
    return conn


class TigerStore(Store):
    backend = "tigergraph"

    @cached_property
    def conn(self):
        return connect()

    def _rows(self, query: str, **params) -> pd.DataFrame:
        res = self.conn.runInstalledQuery(query, params=params)
        d = pd.DataFrame([{**v["attributes"], "TransactionID": int(v["v_id"])} for v in res[0]["txns"]], columns=COLUMNS)
        d["ts"] = pd.to_datetime(d["ts"])
        # TigerGraph has no NULL: loaded blanks come back as "" or 0. Restore the missing values signals.py expects.
        for c in ("addr1", "addr2", "dist1"):
            d[c] = d[c].where(d[c] != 0)
        for c in ("ProductCD", "card4", "card6", "P_emaildomain", "R_emaildomain", "M4", "M6", "DeviceType", "id_15", "id_23"):
            d[c] = d[c].replace("", None)
        return d.sort_values("ts").reset_index(drop=True)

    def card_txns(self, card_id: str) -> pd.DataFrame:
        return self._rows("card_txns", card_id=card_id)

    def device_txns(self, device: str, start, end) -> pd.DataFrame:
        clamp = lambda t: min(max(pd.Timestamp(t), pd.Timestamp("2016-01-01")), pd.Timestamp("2017-12-31")).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
        return self._rows("device_txns", device=device, t0=clamp(start), t1=clamp(end))

    def txn_cases(self, txn_ids) -> list[str]:
        if not txn_ids:
            return []
        res = self.conn.runInstalledQuery("txn_cases", params={"txns": [str(t) for t in txn_ids]})
        return sorted(v["v_id"] for v in res[0]["cases"])

    def write_case(self, record: dict) -> str | None:
        a = record["answer"]
        gid = f"CASE-2016-{record['case_id'].split('-')[1]}"
        c = a["case"]
        self.conn.upsertVertex("InvestigationCase", gid, {
            "hhg_id": record["case_id"], "status": c["status"], "verdict": c["verdict"], "pattern": c["pattern"],
            "fraud_probability": c["fraud_probability"], "exposure_usd": c["exposure_usd"], "summary": c["summary"],
            "answer_json": json.dumps(a),
        })
        self.conn.upsertEdge("InvestigationCase", gid, "INVESTIGATES", "Card", record["card_id"])
        for t in record["affected"]:
            self.conn.upsertEdge("InvestigationCase", gid, "AFFECTS", "Transaction", t)
        for cc in record["similar"]:
            self.conn.upsertEdge("InvestigationCase", gid, "SIMILAR_TO", "ClosedCase", cc)
        for card in record["connected"]:
            self.conn.upsertEdge("InvestigationCase", gid, "CONNECTS", "Card", card)
        return gid


def export_csv() -> Path:
    """Vertex/edge CSVs for the loading job, from the local cache (build it first with data.Store().tx)."""
    out = CACHE / "load"
    out.mkdir(parents=True, exist_ok=True)
    st = Store()
    tx = st.tx.copy()
    tx["ts"] = tx["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    tx["device_specific"] = tx["device_specific"].astype(int)
    tx["addr1"] = tx["addr1"].map(lambda x: "" if pd.isna(x) else f"{x:.0f}")  # region ids: "204", not "204.0"
    tx.to_csv(out / "transactions.csv", index=False)
    st.closed.to_csv(out / "closed_cases.csv", index=False)
    cc = st.closed.assign(t=st.closed["txn_ids"].str.split("|")).explode("t")
    cc[["case_id", "t"]].to_csv(out / "case_txn.csv", index=False)
    con = st.closed.assign(c=st.closed["connected_card_ids"].str.split("|")).explode("c")
    con[con["c"].astype(bool)][["case_id", "c"]].to_csv(out / "case_connected.csv", index=False)
    return out


def setup() -> None:
    conn = connect()
    print(conn.gsql((GSQL / "schema.gsql").read_text()))
    out = export_csv()
    print(conn.gsql((GSQL / "load.gsql").read_text()))
    # REST uploads are size-limited, so the ~90 MB transaction file goes in 50k-row chunks.
    for i, chunk in enumerate(pd.read_csv(out / "transactions.csv", chunksize=50_000, dtype=str, keep_default_na=False)):
        part = out / "tx_part.csv"
        chunk.to_csv(part, index=False)
        print("load_tx part", i, conn.runLoadingJobWithFile(str(part), "f_tx", "load_tx", sep=","))
    for job, fname, f in [("load_cases", "f_cases", "closed_cases.csv"),
                          ("load_case_txn", "f_ct", "case_txn.csv"), ("load_case_conn", "f_cc", "case_connected.csv")]:
        print(job, conn.runLoadingJobWithFile(str(out / f), fname, job, sep=","))
    print(conn.gsql((GSQL / "queries.gsql").read_text()))


if __name__ == "__main__" and sys.argv[1:] == ["setup"]:
    setup()
