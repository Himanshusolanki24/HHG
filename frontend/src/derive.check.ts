// Self-check: fixtures validate against the zod schemas and the derived decision logic holds.
// Run: npm run check
import assert from 'node:assert/strict'
import { fixtures } from './api/mock.ts'
import { band, diffRecs, evidencePath, liveStatus, recommendations, visibleSteps } from './derive.ts'

assert.equal(fixtures.cases.length, 20)
assert.deepEqual(Object.keys(fixtures.investigations).sort(), ['FC-1041', 'FC-1042', 'FC-1043'])
assert.deepEqual([band(0.39), band(0.4), band(0.7)], ['low', 'medium', 'high'])

const policyIds = new Set(fixtures.policies.map((p) => p.id))
for (const inv of Object.values(fixtures.investigations)) {
  const nodeIds = new Set(inv.nodes.map((n) => n.id))
  const edgeIds = new Set(inv.edges.map((e) => e.id))
  const evIds = new Set(inv.steps.flatMap((s) => (s.evidence ? [s.evidence.id] : [])))
  for (const s of inv.steps) {
    s.nodes.forEach((n) => assert(nodeIds.has(n), `${inv.caseId} ${s.id}: unknown node ${n}`))
    s.edges.forEach((e) => assert(edgeIds.has(e), `${inv.caseId} ${s.id}: unknown edge ${e}`))
    for (const c of s.claims) {
      const ok = { node: nodeIds, policy: policyIds, evidence: evIds }[c.ref.kind].has(c.ref.id)
      assert(ok, `${inv.caseId} ${s.id}: claim "${c.text}" points at missing ${c.ref.kind} ${c.ref.id}`)
    }
    const r = s.recommendation
    if (r) {
      assert(r.riskLo <= r.risk && r.risk <= r.riskHi, `${r.id}: risk outside its interval`)
      assert(policyIds.has(r.policyId), `${r.id}: unknown policy`)
      r.actions.forEach((a) => assert(policyIds.has(a.policyId), `${r.id}: action ${a.id} unknown policy`))
      r.causedBy.forEach((e) => assert(evIds.has(e), `${r.id}: causedBy missing ${e}`))
    }
  }
}

// The flip case: recommendation and route change, freeze becomes allowed.
const steps = fixtures.investigations['FC-1042'].steps
const { prior, current } = recommendations(steps)
assert(prior && current && prior.action !== current.action)
const diff = diffRecs(prior, current)
assert(diff.find((r) => r.field === 'Action')!.changed)
assert.equal(diff.find((r) => r.field === 'Risk')!.delta, 37)
assert(diff.find((r) => r.field === 'Actions unlocked')!.after.includes('Freeze account'))

// Replay cursor: before the flip there is only one recommendation, and the case waits on evidence.
const early = visibleSteps(steps, 6)
assert.equal(recommendations(early).prior, undefined)
assert.equal(liveStatus('open', early, false), 'awaiting_evidence')
assert.equal(liveStatus('open', steps, true), 'ready_to_act')
assert.equal(liveStatus('closed', steps, true), 'closed')
assert(evidencePath(early).nodes.has('dev:7f3a') && !evidencePath(early).nodes.has('case:0877'))

console.log('derive.check: ok')
