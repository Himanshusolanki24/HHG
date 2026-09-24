import { create } from 'zustand'
import type { AgentStep, AuditEntry } from './api/schemas.ts'

export type Tab = 'graph' | 'timeline' | 'trace' | 'record'
interface Run { steps: AgentStep[]; done: boolean; error?: string }

interface State {
  selectedId: string | null
  tab: Tab
  runs: Record<string, Run>
  cursor: number | null // replay position; null = live
  playing: boolean
  focusNode: string | null
  focusStep: string | null
  evidenceOnly: boolean
  audit: AuditEntry[]
  theme: 'dark' | 'light'
  select: (id: string) => void
  setTab: (t: Tab) => void
  startRun: (id: string) => void
  pushStep: (id: string, s: AgentStep) => void
  endRun: (id: string, error?: string) => void
  setCursor: (c: number | null) => void
  setPlaying: (p: boolean) => void
  showNode: (id: string | null) => void
  showStep: (id: string) => void
  toggleEvidenceOnly: () => void
  addAudit: (a: AuditEntry) => void
  patchAudit: (id: string, p: Partial<AuditEntry>) => void
  toggleTheme: () => void
}

export const useStore = create<State>((set) => ({
  selectedId: null,
  tab: 'graph',
  runs: {},
  cursor: null,
  playing: false,
  focusNode: null,
  focusStep: null,
  evidenceOnly: false,
  audit: [],
  theme: 'dark',
  select: (id) => set({ selectedId: id, cursor: null, playing: false, focusNode: null }),
  setTab: (tab) => set({ tab }),
  startRun: (id) => set((s) => ({ runs: { ...s.runs, [id]: { steps: [], done: false } } })),
  pushStep: (id, step) => set((s) => ({ runs: { ...s.runs, [id]: { ...s.runs[id], steps: [...s.runs[id].steps, step] } } })),
  endRun: (id, error) => set((s) => ({ runs: { ...s.runs, [id]: { ...s.runs[id], done: true, error } } })),
  setCursor: (cursor) => set({ cursor }),
  setPlaying: (playing) => set({ playing }),
  showNode: (focusNode) => set(focusNode ? { focusNode, tab: 'graph' } : { focusNode }),
  showStep: (focusStep) => set({ focusStep, tab: 'trace' }),
  toggleEvidenceOnly: () => set((s) => ({ evidenceOnly: !s.evidenceOnly })),
  addAudit: (a) => set((s) => ({ audit: [a, ...s.audit] })),
  patchAudit: (id, p) => set((s) => ({ audit: s.audit.map((a) => (a.id === id ? { ...a, ...p } : a)) })),
  toggleTheme: () => set((s) => {
    const theme = s.theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = theme
    return { theme }
  }),
}))
