import { z } from 'zod'
import * as S from './schemas.ts'
import type { Api } from './client.ts'
import cases from '../fixtures/cases.json' with { type: 'json' }
import policies from '../fixtures/policies.json' with { type: 'json' }
import fc1041 from '../fixtures/FC-1041.json' with { type: 'json' }
import fc1042 from '../fixtures/FC-1042.json' with { type: 'json' }
import fc1043 from '../fixtures/FC-1043.json' with { type: 'json' }

// Fixtures go through the same zod schemas as the real backend, so a bad fixture fails loudly.
export const fixtures = {
  cases: z.array(S.Case).parse(cases),
  policies: z.array(S.Policy).parse(policies),
  investigations: Object.fromEntries(
    [fc1041, fc1042, fc1043].map((f) => { const inv = S.Investigation.parse(f); return [inv.caseId, inv] }),
  ) as Record<string, S.Investigation>,
}

/** Demo knobs: stream speed and a one-shot write failure to show optimistic rollback. */
export const mockControl = { speed: 1, failNext: false }

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

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
        await wait((step.delayMs ?? 800) / mockControl.speed)
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
      throw new Error(`${label} rejected by case service: write conflict on FraudCase ${caseId}`)
    }
    return { id: crypto.randomUUID(), at: new Date().toISOString(), caseId, actionId, label, actor: 'analyst.jdoe', status: 'committed' }
  },
}
