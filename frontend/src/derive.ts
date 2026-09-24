import type { AgentStep, AuditEntry, Case, CaseStatus, Recommendation } from './api/schemas.ts'
import type { InvestigationMeta } from './api/client.ts'

export type Band = 'low' | 'medium' | 'high'
export const band = (risk: number): Band => (risk >= 0.7 ? 'high' : risk >= 0.4 ? 'medium' : 'low')

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

export function liveStatus(base: CaseStatus, steps: AgentStep[], done: boolean): CaseStatus {
  if (base === 'closed') return base
  const req = steps.findLastIndex((s) => s.tool === 'evidence_request')
  if (req >= 0 && !steps.slice(req).some((s) => s.tool === 'evidence_response')) return 'awaiting_evidence'
  if (done && recommendations(steps).current) return 'ready_to_act'
  return base
}

export interface DiffRow { field: string; before: string; after: string; changed: boolean; delta?: number }

const pct = (n: number) => (n * 100).toFixed(0)
const ROUTE: Record<Recommendation['route'], string> = {
  auto_execute: 'Auto-execute', analyst_approval: 'Analyst approval', dual_approval: 'Dual approval',
}
export const routeLabel = (r: Recommendation['route']) => ROUTE[r]

export function diffRecs(a: Recommendation, b: Recommendation): DiffRow[] {
  const allowed = (r: Recommendation) => r.actions.filter((x) => x.allowed).map((x) => x.label)
  const unlocked = allowed(b).filter((l) => !allowed(a).includes(l))
  const openU = (r: Recommendation) => r.unknowns.filter((u) => !u.resolved).length
  const rows: DiffRow[] = [
    { field: 'Action', before: a.action, after: b.action, changed: a.action !== b.action },
    { field: 'Approval route', before: ROUTE[a.route], after: ROUTE[b.route], changed: a.route !== b.route },
    { field: 'Risk', before: pct(a.risk), after: pct(b.risk), changed: a.risk !== b.risk, delta: Math.round((b.risk - a.risk) * 100) },
    { field: 'Risk band (90% CI)', before: `${pct(a.riskLo)}–${pct(a.riskHi)}`, after: `${pct(b.riskLo)}–${pct(b.riskHi)}`, changed: a.riskLo !== b.riskLo || a.riskHi !== b.riskHi, delta: Math.round((b.riskHi - b.riskLo - (a.riskHi - a.riskLo)) * 100) },
    { field: 'Confidence', before: pct(a.confidence), after: pct(b.confidence), changed: a.confidence !== b.confidence, delta: Math.round((b.confidence - a.confidence) * 100) },
    { field: 'Policy cited', before: a.policyId, after: b.policyId, changed: a.policyId !== b.policyId },
    { field: 'Open unknowns', before: String(openU(a)), after: String(openU(b)), changed: openU(a) !== openU(b), delta: openU(b) - openU(a) },
  ]
  if (unlocked.length) rows.push({ field: 'Actions unlocked', before: '', after: unlocked.join(', '), changed: true })
  return rows
}

/** The FraudCase vertex + edges as the agent writes them back to TigerGraph. */
export function caseRecord(c: Case, inv: InvestigationMeta, steps: AgentStep[], audit: AuditEntry[]) {
  const { current, prior } = recommendations(steps)
  const path = evidencePath(steps)
  return {
    vertex: 'FraudCase',
    primary_id: c.id,
    attributes: {
      title: c.title,
      trigger: c.trigger,
      pattern: c.pattern,
      subject: inv.subjectId,
      alert_at: inv.alertAt,
      risk: current?.risk ?? c.risk,
      risk_ci: current ? [current.riskLo, current.riskHi] : null,
      confidence: current?.confidence ?? c.confidence,
      recommendation: current?.action ?? null,
      approval_route: current?.route ?? null,
      prior_recommendation: prior?.action ?? null,
      agent_steps: steps.length,
      tokens: steps.reduce((n, s) => n + s.tokens.in + s.tokens.out, 0),
    },
    edges: [
      { type: 'INVESTIGATES', to: inv.subjectId },
      ...[...path.nodes].map((id) => ({ type: 'SUPPORTED_BY', to: id })),
      ...steps.flatMap((s) => (s.evidence ? [{ type: 'HAS_EVIDENCE', to: s.evidence.id, source: s.evidence.source }] : [])),
      ...(current ? [{ type: 'CITES_POLICY', to: current.policyId }] : []),
      ...audit.filter((a) => a.caseId === c.id && a.status === 'committed').map((a) => ({ type: 'ACTIONED', to: a.actionId, at: a.at, by: a.actor })),
    ],
  }
}
