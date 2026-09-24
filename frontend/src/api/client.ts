import { z } from 'zod'
import * as S from './schemas.ts'
import { mockApi } from './mock.ts'

export const InvestigationMeta = S.Investigation.omit({ steps: true })
export type InvestigationMeta = z.infer<typeof InvestigationMeta>

export interface StreamHandlers {
  onStep: (step: S.AgentStep) => void
  onDone: () => void
  onError: (err: Error) => void
}

export interface Api {
  listCases(): Promise<S.Case[]>
  listPolicies(): Promise<S.Policy[]>
  getInvestigation(caseId: string): Promise<InvestigationMeta | null>
  /** Streams agent steps; returns a cancel function. */
  streamSteps(caseId: string, h: StreamHandlers): () => void
  executeAction(caseId: string, actionId: string, label: string): Promise<S.AuditEntry>
}

// FastAPI contract:
//   GET  /cases                       -> Case[]
//   GET  /policies                    -> Policy[]
//   GET  /cases/{id}/investigation    -> Investigation without steps (404 = no run)
//   GET  /cases/{id}/stream   (SSE)   -> event: step {AgentStep} ... event: done
//   POST /cases/{id}/actions {actionId,label} -> AuditEntry
function httpApi(base: string): Api {
  const get = async <T>(path: string, schema: z.ZodType<T>) => {
    const res = await fetch(base + path)
    if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
    return schema.parse(await res.json())
  }
  return {
    listCases: () => get('/cases', z.array(S.Case)),
    listPolicies: () => get('/policies', z.array(S.Policy)),
    async getInvestigation(id) {
      const res = await fetch(`${base}/cases/${id}/investigation`)
      if (res.status === 404) return null
      if (!res.ok) throw new Error(`investigation ${id}: HTTP ${res.status}`)
      return InvestigationMeta.parse(await res.json())
    },
    streamSteps(id, h) {
      const es = new EventSource(`${base}/cases/${id}/stream`)
      es.addEventListener('step', (e) => {
        const parsed = S.AgentStep.safeParse(JSON.parse((e as MessageEvent).data))
        if (parsed.success) h.onStep(parsed.data)
        else h.onError(new Error(`Malformed step from agent: ${parsed.error.message}`))
      })
      es.addEventListener('done', () => { es.close(); h.onDone() })
      es.onerror = () => { es.close(); h.onError(new Error('Agent stream disconnected')) }
      return () => es.close()
    },
    async executeAction(id, actionId, label) {
      const res = await fetch(`${base}/cases/${id}/actions`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ actionId, label }),
      })
      if (!res.ok) throw new Error(`${label} failed: HTTP ${res.status}`)
      return S.AuditEntry.parse(await res.json())
    },
  }
}

const BASE = import.meta.env.VITE_API_URL as string | undefined
export const isMock = !BASE
export const api: Api = BASE ? httpApi(BASE) : mockApi
