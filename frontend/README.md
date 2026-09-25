# Case Desk: fraud investigation console

Analyst console for the HHG fraud agent. Three panes: case queue, investigation canvas (graph, timeline, agent trace, answer file)
and the decision panel. By default it shows the agent's real runs (`src/fixtures/`, copied from `backend/runs/` by `npm run sync`).

## Run

```bash
npm install
npm run sync         # copy the latest agent output from ../backend/runs
npm run dev          # http://localhost:5173, component library at /kitchen-sink
npm run check        # runs validate against the zod schemas; trace and answer file agree
npm run build
```

Live mode streams a fresh agent run per case over SSE:

```bash
VITE_API_URL=http://localhost:8000 npm run dev   # with `uvicorn api:app --port 8000` running in ../backend
```

| Method | Path | Returns |
|---|---|---|
| GET | `/cases` | Queue rows (`Case[]`) |
| GET | `/policies` | Policy rules R1–R10, 3a, §6 |
| GET | `/cases/{id}/investigation` | Graph, transactions, similar cases, answer file |
| GET (SSE) | `/cases/{id}/stream` | Re-runs the agent: `event: step` per step, then `event: done` |
| POST | `/cases/{id}/actions` `{actionId,label}` | Audit entry. Only `auto` actions run; L1/L2 return 403 naming the approver |

## Keyboard

`j` / `k` move in the queue, `Enter` opens. `1`–`4` switch tabs. In the graph, arrow keys move between entities and `Esc` clears.
Every dotted-underlined number or claim takes focus and shows its source.

## 90-second demo script

| Time | Do | Say |
|---|---|---|
| 0:00 | Queue visible. Click **HHG-014**. | "20 exam cases. This one came from an analyst: several cards this month used the same unusual device." |
| 0:08 | Watch the trace stream (tab `3`). | "Each step is a graph query or retrieval, with latency and token cost. It pulls the card, the 48-hour window, then walks the device to its other cards." |
| 0:20 | Tab `1`, Graph. | "One Samsung profile, always behind an anonymous proxy, used on 27 other cards in 30 days. The agent also found three closed cases from an August ring with the same profile." |
| 0:32 | Point at **Before evidence**. | "Probability 0.82, but blocking needs the cardholder's denial under R2, so it verifies first, opens a case, flags the report and monitors the 27 cards." |
| 0:42 | The reply lands; before/after animates. | "The simulated reply is a denial. Probability rises to 0.98 and BLOCK_CARD is added at L1. The diff shows exactly what changed and which evidence caused it." |
| 0:55 | Hover the disabled **BLOCK_CARD L1** button. | "The agent may only run auto actions. The block waits for a team lead, per policy §2." |
| 1:02 | Click **HHG-010**. | "Contrast: a $1,000 online purchase scored 0.90 by the bank model. The agent says 8%: new device, high score, and its case memory shows cleared new-phone and travel alerts just like it. It closes without bothering the customer." |
| 1:15 | Tab `4`, **Download**. | "This is the answer file we submit: evidence with sources, both recommendations, the report, and the stop reason." |
| 1:25 | Click **Replay investigation**. | "Replay rewinds every pane together for review." |
