# Case Desk: fraud investigation console

Analyst console for a TigerGraph-backed fraud agent. Three panes: case queue, investigation canvas (graph, timeline, agent trace, case record) and the decision panel. By default it runs entirely on fixture JSON. Nothing else is needed.

## Run

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (mock adapter, no backend)
npm run check        # validates every fixture against the zod schemas + asserts decision logic
npm run build
```

Component library: `http://localhost:5173/kitchen-sink`

### Real backend

```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

The FastAPI contract (all responses are zod-validated in `src/api/client.ts`):

| Method | Path | Returns |
|---|---|---|
| GET | `/cases` | `Case[]` |
| GET | `/policies` | `Policy[]` |
| GET | `/cases/{id}/investigation` | `Investigation` without `steps` (404 = no run) |
| GET (SSE) | `/cases/{id}/stream` | `event: step` with an `AgentStep`, then `event: done` |
| POST | `/cases/{id}/actions` `{actionId, label}` | `AuditEntry` |

## Layout

```
src/api/schemas.ts     zod: Case, Policy, GraphNode/Edge, Evidence, Claim, AgentStep, Recommendation, Investigation, AuditEntry
src/api/client.ts      Api interface + HTTP/SSE adapter; picks mock when VITE_API_URL is unset
src/api/mock.ts        fixture adapter with paced streaming and a "fail next action" knob
src/fixtures/          20 queue cases, 10 policy clauses, 3 full investigations
src/derive.ts          pure logic: replay window, current/prior recommendation, diff, evidence path, case record
src/store.ts           Zustand: selection, streamed runs, replay cursor, audit trail, theme
src/components/        CaseQueue, GraphView, Timeline, AgentTrace, CaseRecord, DecisionPanel, ReplayBar, ui (shadcn-style)
```

Every pane is derived from one replay cursor over the streamed steps. Scrub it and the graph highlight, timeline markers, trace, risk gauge and before/after comparison all rewind together.

## Fixture investigations

- **FC-1041 card testing.** Same action, but the route moves from analyst approval to auto-execute once policy CARD-2.1 §3 is confirmed. The risk band narrows.
- **FC-1042 mule network. The recommendation flips.** It starts as "step-up auth and monitor" (risk 52, wide band, confidence 48). Device telemetry arrives after an 18-minute wait and shows device 7F3A is shared with two accounts from CASE-0877, a confirmed mule ring. The recommendation becomes "freeze account and file SAR" with dual approval (risk 89, confidence 86), and the freeze action unlocks.
- **FC-1043 APP scam.** The customer's report triggers a recall. The beneficiary bank confirms the funds are still there, which adds a beneficiary hold.

The other 17 queue cases have queue data only.

## Keyboard

`j` / `k` move in the queue, `Enter` opens. `1`–`4` switch tabs. In the graph, arrow keys move between entities and `Esc` clears. Every number with a dotted underline can take focus and shows its source.

## 90-second demo script

| Time | Do | Say |
|---|---|---|
| 0:00 | Page loaded, queue on the left. Press `j` then `Enter` on **FC-1042**. | "20 benchmark cases. This one was raised by an analyst: six transfers in, then a crypto cash-out." |
| 0:10 | Watch the trace stream on the **Agent trace** tab (`3`). | "Each step is a GSQL query, GraphRAG retrieval or policy lookup, with its latency and token cost. Skeletons mark what's still coming." |
| 0:20 | Point at the decision panel as the first recommendation lands. | "Step-up auth and monitor. Risk 52, but look at the hatched band, 31 to 74, and confidence 48. The agent is saying it doesn't know yet." |
| 0:28 | Point at **What is still unknown**. | "It ranks what it doesn't know by expected information gain. The device question is worth 0.62 bits, so it asks the mobile risk SDK." |
| 0:35 | Hover the disabled **Freeze account** button. | "Freeze is blocked, and the tooltip names the clause: ACC-1.4 §3." |
| 0:42 | Evidence arrives and the panel animates. | "The telemetry comes back. The device is bound to two accounts from a confirmed mule ring. Watch the old recommendation move aside, the new one slide in, and the diff show what changed and which evidence caused it." |
| 0:55 | Click **Show in graph** under *Caused by*, then toggle **Show evidence path only**. | "Here's the exact subgraph the agent relied on: subject, device, the linked accounts, CASE-0877. Everything else is dimmed." |
| 1:05 | Click **Replay investigation** and drag the scrubber back to step 6. | "Replay rewinds every pane together: graph, timeline, gauge and recommendation." |
| 1:15 | Click **Jump to latest**, then **Freeze account** and confirm. | "Freeze is unlocked now. Confirming writes to the audit trail right away and closes the case in the queue." |
| 1:22 | Tick **Fail next action**, run **Require step-up auth**. | "If the write fails, the UI rolls back and says why." |
| 1:28 | Tab `4`, **Copy JSON**. | "And this is the case record written back to TigerGraph." |
