import type { Action, AgentStep, Answer, CaseStatus, Recommendation } from './api/schemas.ts'

export type Band = 'low' | 'medium' | 'high'
export const band = (risk: number): Band => (risk >= 0.7 ? 'high' : risk >= 0.3 ? 'medium' : 'low')

/** Replay cursor: null = live (everything received so far). */
export const visibleSteps = (steps: AgentStep[], cursor: number | null) =>
  cursor === null ? steps : steps.slice(0, cursor)

export function recommendations(steps: AgentStep[]) {
  const recs = steps.flatMap((s) => (s.recommendation ? [s.recommendation] : []))
  return { current: recs.at(-1), prior: recs.at(-2) }
}

/** Nodes/edges the agent actually touched: the evidence subgraph. */
export function evidencePath(steps: AgentStep[]) {
  return {
    nodes: new Set(steps.flatMap((s) => s.nodes)),
    edges: new Set(steps.flatMap((s) => s.edges)),
  }
}

/** Queue status from where the run is: waiting on the customer, a recommendation needing a human approver, or closed. */
export function liveStatus(base: CaseStatus, steps: AgentStep[], done: boolean): CaseStatus {
  if (base === 'closed' && done) return base
  const req = steps.findLastIndex((s) => s.tool === 'evidence_request')
  if (req >= 0 && !steps.slice(req).some((s) => s.tool === 'evidence_response')) return 'awaiting_evidence'
  const { current } = recommendations(steps)
  if (!done || !current) return 'open'
  return current.verdict === 'legitimate' ? 'closed' : 'ready_to_act'
}

export const rule = (a: Action) => a.reason.split(':')[0]
export const ROUTE_LABEL: Record<Action['route'], string> = { auto: 'Auto', L1: 'Team lead (L1)', L2: 'Fraud manager (L2)' }
export const PATTERN_LABEL: Record<Recommendation['pattern'], string> = {
  card_testing: 'Card testing', card_not_present_fraud: 'Card-not-present', card_not_present_new_device: 'Card-not-present, new device',
  out_of_region_use: 'Out-of-region use', account_takeover: 'Account takeover', undocumented: 'Undocumented pattern', none: 'No fraud',
}

export interface DiffRow { field: string; before: string; after: string; changed: boolean; delta?: number }

const pct = (n: number) => (n * 100).toFixed(0)
const names = (r: Recommendation) => r.actions.map((a) => a.action)

export function diffRecs(a: Recommendation, b: Recommendation): DiffRow[] {
  const added = names(b).filter((x) => !names(a).includes(x))
  const dropped = names(a).filter((x) => !names(b).includes(x))
  const needsHuman = (r: Recommendation) => r.actions.filter((x) => x.route !== 'auto').map((x) => `${x.action} (${x.route})`).join(', ') || 'none'
  const files = (r: Recommendation) => (names(r).includes('FILE_REPORT') ? 'Yes' : 'No')
  return [
    { field: 'Verdict', before: a.verdict, after: b.verdict, changed: a.verdict !== b.verdict },
    { field: 'Fraud probability', before: pct(a.p), after: pct(b.p), changed: a.p !== b.p, delta: Math.round((b.p - a.p) * 100) },
    { field: '90% band', before: `${pct(a.pLo)}–${pct(a.pHi)}`, after: `${pct(b.pLo)}–${pct(b.pHi)}`, changed: a.pLo !== b.pLo || a.pHi !== b.pHi, delta: Math.round((b.pHi - b.pLo - (a.pHi - a.pLo)) * 100) },
    { field: 'Pattern', before: PATTERN_LABEL[a.pattern], after: PATTERN_LABEL[b.pattern], changed: a.pattern !== b.pattern },
    { field: 'Actions added', before: '', after: added.join(', ') || 'none', changed: added.length > 0 },
    { field: 'Actions dropped', before: dropped.join(', ') || 'none', after: '', changed: dropped.length > 0 },
    { field: 'Needs a human', before: needsHuman(a), after: needsHuman(b), changed: needsHuman(a) !== needsHuman(b) },
    { field: 'Suspicious activity report', before: files(a), after: files(b), changed: files(a) !== files(b) },
  ]
}

/** The answer file is the case record: what the grader reads and what the agent wrote to the graph. */
export const caseRecord = (answer: Answer) => answer
