// Self-check: the agent's real runs validate against the UI schemas and the derived decision logic holds.
// Run: npm run check   (after `npm run sync`)
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { z } from 'zod'
import * as S from './api/schemas.ts'
import { diffRecs, evidencePath, liveStatus, recommendations, visibleSteps } from './derive.ts'

const dir = new URL('./fixtures/', import.meta.url)
const read = (f: string) => JSON.parse(readFileSync(new URL(f, dir), 'utf8'))
const queue = z.array(S.Case).parse(read('queue.json'))
z.array(S.Policy).parse(read('policies.json'))
const runs = Object.fromEntries(readdirSync(dir).filter((f) => f.startsWith('HHG-')).map((f) => { const r = S.Investigation.parse(read(f)); return [r.caseId, r] }))

assert.equal(queue.length, 20)
assert.equal(Object.keys(runs).length, 20)

for (const r of Object.values(runs)) {
  const ids = new Set(r.nodes.map((n) => n.id))
  r.edges.forEach((e) => assert(ids.has(e.source) && ids.has(e.target), `${r.caseId}: dangling edge ${e.id}`))
  const { current } = recommendations(r.steps)
  assert(current, `${r.caseId}: no recommendation`)
  assert.deepEqual(current.actions, r.answer.next_best_actions.final, `${r.caseId}: trace and answer file disagree`)
}

// HHG-014: the reply turns verify-first into a block; before it arrives the case waits on evidence.
const steps = runs['HHG-014'].steps
const { prior, current } = recommendations(steps)
assert(prior && current)
const added = diffRecs(prior, current).find((d) => d.field === 'Actions added')!
assert(added.after.includes('BLOCK_CARD'))
const req = steps.findIndex((s) => s.tool === 'evidence_request')
assert.equal(liveStatus('open', visibleSteps(steps, req + 1), false), 'awaiting_evidence')
assert.equal(liveStatus('open', steps, true), 'ready_to_act')
assert(evidencePath(steps).nodes.size > 3)

console.log('derive.check: ok')
