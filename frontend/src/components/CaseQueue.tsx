import { useEffect, useMemo, useRef, useState } from 'react'
import { useCases } from '../hooks.ts'
import { useStore } from '../store.ts'
import { liveStatus } from '../derive.ts'
import { isMock } from '../api/client.ts'
import type { Case, CaseStatus, Pattern } from '../api/schemas.ts'
import { Prov, RiskChip, Skeleton, cn } from './ui.tsx'

export const STATUS: Record<CaseStatus, string> = {
  open: 'Open', awaiting_evidence: 'Awaiting evidence', ready_to_act: 'Ready to act', closed: 'Closed',
}
export const TRIGGER: Record<Case['trigger'], string> = {
  risk_score: 'Risk score', customer_report: 'Customer report', analyst_request: 'Analyst request',
}
export const PATTERN: Record<Pattern, string> = {
  card_testing: 'Card testing', account_takeover: 'Account takeover', mule_network: 'Mule network',
  app_scam: 'APP scam', synthetic_identity: 'Synthetic identity', friendly_fraud: 'Friendly fraud',
}

// ponytail: mock mode pins "now" to the fixture day so time-in-state reads sensibly on any date.
const NOW = isMock ? Date.parse('2026-09-24T09:58:00Z') : Date.now()
export function since(iso: string) {
  const m = Math.max(0, Math.round((NOW - Date.parse(iso)) / 60000))
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`
}

const isTyping = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /INPUT|SELECT|TEXTAREA/.test(t.tagName))

export function CaseQueue() {
  const { data, isLoading, error } = useCases()
  const runs = useStore((s) => s.runs)
  const selectedId = useStore((s) => s.selectedId)
  const select = useStore((s) => s.select)
  const [status, setStatus] = useState<CaseStatus | 'all'>('all')
  const [pattern, setPattern] = useState<Pattern | 'all'>('all')
  const [active, setActive] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  const rows = useMemo(() => (data ?? [])
    .map((c) => ({ ...c, status: runs[c.id] ? liveStatus(c.status, runs[c.id].steps, runs[c.id].done) : c.status }))
    .filter((c) => (status === 'all' || c.status === status) && (pattern === 'all' || c.pattern === pattern)),
  [data, runs, status, pattern])

  const activeIdx = Math.min(active, Math.max(0, rows.length - 1))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'j' || e.key === 'k') {
        e.preventDefault()
        setActive((i) => Math.max(0, Math.min(rows.length - 1, Math.min(i, rows.length - 1) + (e.key === 'j' ? 1 : -1))))
      } else if (e.key === 'Enter' && (e.target === document.body || listRef.current?.contains(e.target as Node))) {
        if (rows[activeIdx]) select(rows[activeIdx].id)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [rows, activeIdx, select])

  useEffect(() => {
    listRef.current?.querySelector(`[data-idx="${activeIdx}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [activeIdx])

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: data?.length ?? 0 }
    for (const r of data ?? []) { const s = runs[r.id] ? liveStatus(r.status, runs[r.id].steps, runs[r.id].done) : r.status; c[s] = (c[s] ?? 0) + 1 }
    return c
  }, [data, runs])

  return (
    <section aria-label="Case queue" className="flex min-h-0 flex-col border-r border-line bg-panel">
      <header className="border-b border-line px-3 pt-2.5 pb-2">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">Case queue</h2>
          <span className="text-2xs text-faint">j / k to move, Enter to open</span>
        </div>
        <div role="radiogroup" aria-label="Filter by status" className="mt-2 flex flex-wrap gap-1">
          {(['all', 'open', 'awaiting_evidence', 'ready_to_act', 'closed'] as const).map((s) => (
            <button
              key={s}
              role="radio"
              aria-checked={status === s}
              onClick={() => setStatus(s)}
              className={cn('h-6 rounded-sm border px-1.5 text-2xs', status === s ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted hover:text-fg')}
            >
              {s === 'all' ? 'All' : STATUS[s]} <span className="text-faint">{counts[s] ?? 0}</span>
            </button>
          ))}
        </div>
        <label className="mt-2 flex items-center gap-2 text-2xs text-muted">
          Pattern
          <select
            value={pattern}
            onChange={(e) => setPattern(e.target.value as Pattern | 'all')}
            className="h-6 flex-1 rounded-sm border border-line bg-bg px-1 text-xs text-fg"
          >
            <option value="all">All patterns</option>
            {Object.entries(PATTERN).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </header>

      <div className="grid grid-cols-[1fr_64px_36px_52px] gap-x-2 border-b border-line px-3 py-1 text-2xs text-faint">
        <span>Case</span><span>Risk</span><span className="text-right">Conf</span><span className="text-right">In state</span>
      </div>

      <div ref={listRef} role="listbox" aria-label="Cases" aria-activedescendant={rows[activeIdx] ? `case-${rows[activeIdx].id}` : undefined} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto">
        {isLoading && Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="space-y-1.5 border-b border-line px-3 py-2.5"><Skeleton className="w-24" /><Skeleton className="w-44" /></div>
        ))}
        {error && <p className="p-3 text-sm text-muted">Could not load cases: {error.message}. Check the API URL and reload.</p>}
        {!isLoading && rows.length === 0 && <p className="p-3 text-sm text-muted">No cases match these filters. Clear a filter to see more.</p>}
        {rows.map((c, i) => (
          <div
            key={c.id}
            id={`case-${c.id}`}
            data-idx={i}
            role="option"
            aria-selected={c.id === selectedId}
            onClick={() => { setActive(i); select(c.id) }}
            className={cn(
              'relative grid cursor-pointer grid-cols-[1fr_64px_36px_52px] gap-x-2 border-b border-line px-3 py-2',
              c.id === selectedId ? 'bg-accent-soft' : 'hover:bg-raised',
              i === activeIdx && 'outline outline-1 -outline-offset-1 outline-accent',
            )}
          >
            {c.id === selectedId && <span className="absolute inset-y-0 left-0 w-0.5 bg-accent" aria-hidden />}
            <div className="min-w-0">
              <div className="font-medium">{c.id}</div>
              <div className="truncate text-xs text-muted" title={c.title}>{c.title}</div>
              <div className="mt-0.5 flex gap-2 whitespace-nowrap text-2xs text-faint">
                <span className="text-muted">{STATUS[c.status]}</span><span className="truncate">{TRIGGER[c.trigger]}</span>
                {c.hasRun && <span className="ml-auto shrink-0 text-accent">Agent run</span>}
              </div>
            </div>
            <div className="text-xs">
              <RiskChip risk={c.risk} />
              <div className="text-muted">{(c.risk * 100).toFixed(0)}</div>
            </div>
            <div className="text-right text-xs text-conf">{(c.confidence * 100).toFixed(0)}</div>
            <div className="text-right text-xs text-muted">
              <Prov source={`case.stateSince = ${c.stateSince}`}>{since(c.stateSince)}</Prov>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
