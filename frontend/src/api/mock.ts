import { z } from 'zod'
import * as S from './schemas.ts'
import type { Api } from './client.ts'
import queue from '../fixtures/queue.json' with { type: 'json' }
import policies from '../fixtures/policies.json' with { type: 'json' }

// Real agent output, copied from backend/runs by `npm run sync`. Same zod schemas as the live API, so drift fails loudly.
const runs = import.meta.glob('../fixtures/HHG-*.json', { eager: true, import: 'default' })

export const fixtures = {
  cases: z.array(S.Case).parse(queue),
  policies: z.array(S.Policy).parse(policies),
  investigations: Object.fromEntries(
    Object.values(runs).map((f) => { const inv = S.Investigation.parse(f); return [inv.caseId, inv] }),
  ) as Record<string, S.Investigation>,
}

/** Demo knobs: stream speed and a one-shot write failure to show optimistic rollback. */
export const mockControl = { speed: 1, failNext: false }

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))
// ponytail: fixture runs have no pacing; approximate the live API's (600 ms a step, longer while waiting on the customer).
const pace = (s: S.AgentStep) => (s.tool === 'evidence_response' ? 2600 : s.tool === 'recommend' ? 1100 : 700)

export const mockApi: Api = {
  listCases: async () => { await wait(250); return fixtures.cases },
  listPolicies: async () => fixtures.policies,
  async getInvestigation(id) {
    await wait(300)
    const inv = fixtures.investigations[id]
    if (!inv) return null
    const { steps: _steps, ...meta } = inv
    return meta
  },
  streamSteps(id, h) {
    const steps = fixtures.investigations[id]?.steps ?? []
    let cancelled = false
    ;(async () => {
      for (const step of steps) {
        await wait(pace(step) / mockControl.speed)
        if (cancelled) return
        h.onStep(step)
      }
      if (!cancelled) h.onDone()
    })()
    return () => { cancelled = true }
  },
  async executeAction(caseId, actionId, label) {
    await wait(900)
    if (mockControl.failNext) {
      mockControl.failNext = false
      throw new Error(`${label} rejected by case service: write conflict on InvestigationCase ${caseId}`)
    }
    return { id: crypto.randomUUID(), at: new Date().toISOString(), caseId, actionId, label, actor: 'analyst.jdoe', status: 'committed' }
  },
}
