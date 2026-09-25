import { useEffect, useRef, useState } from 'react'
import type { CaseView } from '../hooks.ts'
import { usePolicies } from '../hooks.ts'
import { useStore } from '../store.ts'
import type { AgentStep, Claim, Evidence } from '../api/schemas.ts'
import { PATTERN_LABEL } from '../derive.ts'
import { Button, Prov, Skeleton, Tag, cn } from './ui.tsx'

export const TOOL: Record<AgentStep['tool'], string> = {
  gsql: 'GSQL query', graphrag: 'GraphRAG retrieval', policy_lookup: 'Policy lookup',
  evidence_request: 'Evidence request', evidence_response: 'Evidence response', recommend: 'Recommendation',
}
const fmtMs = (ms: number) => (ms >= 60000 ? `${(ms / 60000).toFixed(1)} min` : ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms} ms`)

export function AgentTrace({ view }: { view: CaseView }) {
  const { steps, streaming, error, allSteps } = view
  const focusStep = useStore((s) => s.focusStep)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [autoOpen, setAutoOpen] = useState(true)
  const end = useRef<HTMLDivElement>(null)

  const last = steps.at(-1)?.id
  const isOpen = (id: string) => open.has(id) || (autoOpen && id === last)
  const toggle = (id: string, o: boolean) => setOpen((s) => { const n = new Set(s); if (o) n.add(id); else n.delete(id); return n })

  useEffect(() => { if (streaming) end.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [steps.length, streaming])
  useEffect(() => {
    if (!focusStep) return
    toggle(focusStep, true)
    requestAnimationFrame(() => document.getElementById(`step-${focusStep}`)?.scrollIntoView({ block: 'center' }))
  }, [focusStep])

  const evidence = Object.fromEntries(allSteps.flatMap((s) => (s.evidence ? [[s.evidence.id, s.evidence]] : [])))
  const latency = steps.reduce((n, s) => n + (s.tool === 'evidence_response' ? 0 : s.latencyMs), 0)
  const tokens = steps.reduce((n, s) => n + s.tokens.in + s.tokens.out, 0)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-4 border-b border-line px-3 py-1.5 text-xs text-muted">
        <span><span className="text-fg">{steps.length}</span> of {allSteps.length}{streaming ? '+' : ''} steps</span>
        <Prov source="sum of step latencyMs, excluding waits on external evidence"><span className="text-fg">{fmtMs(latency)}</span> compute</Prov>
        <Prov source="sum of tokens.in + tokens.out across steps"><span className="text-fg">{tokens.toLocaleString()}</span> tokens</Prov>
        <div className="ml-auto flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => { setAutoOpen(false); setOpen(new Set(steps.map((s) => s.id))) }}>Expand all</Button>
          <Button size="sm" variant="ghost" onClick={() => { setAutoOpen(false); setOpen(new Set()) }}>Collapse all</Button>
        </div>
      </div>
      <div role="log" aria-live="polite" aria-label="Agent reasoning trace" className="min-h-0 flex-1 overflow-y-auto">
        <ol>
          {steps.map((s) => (
            <li key={s.id} id={`step-${s.id}`} className={cn('border-b border-line', focusStep === s.id && 'bg-accent-soft')}>
              <details open={isOpen(s.id)} onToggle={(e) => { const o = (e.target as HTMLDetailsElement).open; if (o !== isOpen(s.id)) { setAutoOpen(false); toggle(s.id, o) } }}>
                <summary className="grid grid-cols-[28px_120px_1fr_auto] items-center gap-2 px-3 py-1.5 hover:bg-raised">
                  <span className="text-xs text-faint">{String(s.seq).padStart(2, '0')}</span>
                  <Tag className={cn(s.tool === 'recommend' && 'border-fg text-fg', s.tool.startsWith('evidence') && 'border-conf text-conf')}>{TOOL[s.tool]}</Tag>
                  <span className="truncate font-medium">{s.title}</span>
                  <span className="flex gap-3 text-2xs text-muted">
                    <Prov source={`step ${s.id}.latencyMs`}>{s.tool === 'evidence_response' ? `waited ${fmtMs(s.latencyMs)}` : fmtMs(s.latencyMs)}</Prov>
                    <Prov source={`step ${s.id}.tokens (in ${s.tokens.in} / out ${s.tokens.out})`}>{s.tokens.in + s.tokens.out ? `${(s.tokens.in + s.tokens.out).toLocaleString()} tok` : 'no LLM'}</Prov>
                    <span>{s.at.slice(11, 19)}</span>
                  </span>
                </summary>
                <StepBody step={s} evidence={evidence} />
              </details>
            </li>
          ))}
        </ol>
        {streaming && (
          <div className="grid grid-cols-[28px_120px_1fr] items-center gap-2 px-3 py-2" aria-label="Waiting for next agent step">
            <Skeleton className="w-4" /><Skeleton className="w-24" /><Skeleton className="w-2/3" />
          </div>
        )}
        {error && <p className="px-3 py-2 text-sm text-risk-high">Stream stopped: {error}. The steps above are complete; reopen the case to retry.</p>}
        {!streaming && steps.length === 0 && <p className="p-3 text-sm text-muted">No agent steps at this replay position. Drag the replay scrubber right to see the run.</p>}
        <div ref={end} />
      </div>
    </div>
  )
}

function StepBody({ step: s, evidence }: { step: AgentStep; evidence: Record<string, Evidence> }) {
  return (
    <div className="space-y-2 px-3 pt-0.5 pb-3 pl-[40px]">
      <pre className="overflow-x-auto rounded-sm border border-line bg-bg px-2 py-1.5 font-mono text-2xs text-muted">{s.input}</pre>
      <p className="max-w-[72ch]">{s.summary}</p>
      {s.claims.length > 0 && (
        <ul className="space-y-1" aria-label="Claims and their support">
          {s.claims.map((c, i) => <li key={i} className="flex items-baseline gap-2 text-xs"><span className="text-faint">Claim</span><ClaimLink claim={c} evidence={evidence} /></li>)}
        </ul>
      )}
      {s.evidence && (
        <div className="rounded-sm border border-line px-2 py-1.5 text-xs">
          <span className="font-medium">{s.evidence.id}</span> <span className="text-muted">{s.evidence.label}: {s.evidence.summary}</span>
          <div className="font-mono text-2xs text-faint">{s.evidence.source}</div>
        </div>
      )}
      {s.recommendation && (
        <div className="rounded-sm border border-line-strong px-2 py-1.5 text-xs">
          <span className="font-medium capitalize">{s.recommendation.verdict}</span>
          <span className="text-muted"> at {(s.recommendation.p * 100).toFixed(0)} ({(s.recommendation.pLo * 100).toFixed(0)}–{(s.recommendation.pHi * 100).toFixed(0)}), {PATTERN_LABEL[s.recommendation.pattern].toLowerCase()}: </span>
          {s.recommendation.actions.map((a) => `${a.action} (${a.route})`).join(', ')}
        </div>
      )}
    </div>
  )
}

/** Every claim resolves to the graph node, policy clause, or evidence item that supports it. */
export function ClaimLink({ claim, evidence = {} }: { claim: Claim; evidence?: Record<string, Evidence> }) {
  const policies = usePolicies()
  const showNode = useStore((s) => s.showNode)
  const { kind, id } = claim.ref
  if (kind === 'node') {
    return (
      <button onClick={() => showNode(id)} className="text-left text-accent underline-offset-2 hover:underline">
        {claim.text} <span className="font-mono text-2xs text-muted">[{id}]</span>
      </button>
    )
  }
  if (kind === 'policy') {
    const p = policies[id]
    return (
      <Prov source={p ? `${p.doc}, ${p.clause}: ${p.title}` : id} detail={p?.text}>
        {claim.text} <span className="font-mono text-2xs text-muted">[{p ? p.clause : id}]</span>
      </Prov>
    )
  }
  const ev = evidence[id]
  return <Prov source={ev?.source ?? `evidence ${id}`} detail={ev ? `${ev.label}: ${ev.summary}` : undefined}>{claim.text} <span className="font-mono text-2xs text-muted">[{id}]</span></Prov>
}
