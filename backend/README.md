# Fraud investigation agent

Investigates the 20 HHG cases on the real dataset. For each case it writes a README-format answer file to
`../cases/` and a UI trace to `runs/`.

## Run

```bash
python3.14 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env          # set DATA_DIR; add MISTRAL_API_KEY and Savanna details when you have them
.venv/bin/python calibrate.py # learn evidence weights from the 5,565 closed cases -> lr.json (about 90 s)
.venv/bin/python agent.py     # all 20 cases -> ../cases/*.json, runs/*.json   (or: agent.py HHG-014)
.venv/bin/python validate.py  # README answer-format + policy checks, must say 20/20 valid
.venv/bin/python test_policy.py
.venv/bin/uvicorn api:app --port 8000   # the console's live API (SSE step stream)
```

The first run builds `.cache/tx.parquet` from the 708 MB CSV, which takes about a minute.

## How a case is investigated

| Step | Code | What it does |
|---|---|---|
| Graph evidence | `signals.py` via `data.Store` / `tg.TigerStore` | Card history, ±48 h window, R5 card-testing sequence, sub-$500 splits, device ring traversal, region vs home region |
| Case memory | `agent.similar_cases` | Closed cases on the same card or shared device, same-typology exemplars, and cases closed earlier in this run |
| Weigh | `lr.json` from `calibrate.py` | Likelihood ratios learned from the closed cases (naive Bayes, tempered ×0.6, capped at 8) |
| Decide | `policy.py` | Rules R1–R10, auto/L1/L2 routes, the case-vs-report rule (3a) and the stopping rule (§6), all in code. The LLM never picks actions. |
| Ask | `agent.investigate` | Picks the permitted request with the highest expected information gain, simulates the reply from the evidence, and recommends again |
| Write | `llm.py` (Mistral, JSON mode) | Summary, report narrative, pattern description. Uses only the facts given; falls back to templates without a key |
| Record | `tg.TigerStore.write_case` | `InvestigationCase` vertex with edges to the card, affected transactions, similar cases and connected cards |

## What the data taught us (measured on closed cases)

- **Card IDs** are not in `transactions.csv`. They are the customer ID plus the rank of the customer's distinct (card4, card6) pairs, with blanks sorted first. This matches 100% of 14,955 closed-case transactions.
- **Pattern rules reproduce the analysts' labels 86.2% of the time** (4,021 / 4,665 confirmed cases).
- **Model score:** every cleared alert scored 0.84–0.92. A high score may only lower the probability, never raise it.
- **New device:** 83% of cleared alerts came from a new device ("customer bought a new phone"), so a new device alone lowers the probability.
- **Device ring:** a real ring is a specific device profile that only ever appears behind one proxy type. The SM-G935F ring is 100% anonymous-proxy across 52 cards; popular profiles such as Windows 10 / Chrome 65 are not rings.
- **Big card buckets:** some cards have 10,000+ transactions (the dataset's customer is an issuer bucket). Counts of same-amount charges and tiny authorizations are confounded by this, so they are not weighted. Recurring charges must repeat at monthly gaps to count for R7.

## TigerGraph

`python tg.py setup` creates the schema (`gsql/schema.gsql`), bulk-loads in 50k-row chunks (`gsql/load.gsql`) and installs the queries
(`gsql/queries.gsql`: `card_txns`, `device_txns`, `txn_cases`, `prior_investigations`). Once `SAVANNA_HOST` resolves, `data.store()` switches
to TigerGraph automatically, and answer files record `written_to_graph: true` with the `graph_case_id`.
