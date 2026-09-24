import { useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from './api/client.ts'
import { useStore } from './store.ts'
import { evidencePath, liveStatus, recommendations, visibleSteps } from './derive.ts'
import type { Case } from './api/schemas.ts'

export const useCases = () => useQuery({ queryKey: ['cases'], queryFn: api.listCases })
export const usePolicies = () => {
  const q = useQuery({ queryKey: ['policies'], queryFn: api.listPolicies, staleTime: Infinity })
  return useMemo(() => Object.fromEntries((q.data ?? []).map((p) => [p.id, p])), [q.data])
}

/** Opens the agent stream for a case once; later visits reuse the received steps. */
export function useAgentStream(c: Case | undefined) {
  useEffect(() => {
    if (!c?.hasRun) return
    const s = useStore.getState()
    if (s.runs[c.id]) return
    s.startRun(c.id)
    // ponytail: streams are never cancelled on case switch so background runs keep filling in.
    api.streamSteps(c.id, {
      onStep: (step) => useStore.getState().pushStep(c.id, step),
      onDone: () => useStore.getState().endRun(c.id),
      onError: (e) => useStore.getState().endRun(c.id, e.message),
    })
  }, [c?.id, c?.hasRun])
}

/** Everything the three panes need for the selected case, derived from the replay cursor. */
export function useCaseView() {
  const cases = useCases()
  const selectedId = useStore((s) => s.selectedId)
  const run = useStore((s) => (selectedId ? s.runs[selectedId] : undefined))
  const cursor = useStore((s) => s.cursor)
  const c = cases.data?.find((x) => x.id === selectedId)
  const inv = useQuery({ queryKey: ['investigation', selectedId], queryFn: () => api.getInvestigation(selectedId!), enabled: !!c?.hasRun })
  useAgentStream(c)
  return useMemo(() => {
    const all = run?.steps ?? []
    const steps = visibleSteps(all, cursor)
    const live = cursor === null
    return {
      c,
      inv: inv.data ?? undefined,
      invLoading: inv.isLoading,
      allSteps: all,
      steps,
      streaming: live && !!run && !run.done,
      error: run?.error,
      ...recommendations(steps),
      path: evidencePath(steps),
      status: c ? (c.hasRun ? liveStatus(c.status, steps, !!run?.done || !live) : c.status) : undefined,
    }
  }, [c, inv.data, inv.isLoading, run, cursor])
}
export type CaseView = ReturnType<typeof useCaseView>
