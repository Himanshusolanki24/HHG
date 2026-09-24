import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, LayoutGroup, animate, motion } from 'motion/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { CaseView } from '../hooks.ts'
import { usePolicies } from '../hooks.ts'
import { useStore } from '../store.ts'
import { api } from '../api/client.ts'
import { band, diffRecs, routeLabel } from '../derive.ts'
import type { ActionOption, AgentStep, AuditEntry, Case, Recommendation, SimilarCase } from '../api/schemas.ts'
import { STATUS } from './CaseQueue.tsx'
import { Button, Confirm, Prov, RiskChip, SectionHead, Skeleton, Tag, Tip, cn, riskBg, riskText } from './ui.tsx'

const pct = (n: number) => (n * 100).toFixed(0)
const EASE = [0.2, 0.7, 0.2, 1] as const
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches

/** Tweens a number in place (transform-free text update, no re-render per frame). */
export function Num({ value, className, signed }: { value: number; className?: string; signed?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null)
  const prev = useRef(value)
  const fmt = (v: number) => `${signed && v > 0 ? '+' : ''}${Math.round(v)}`
  useEffect(() => {
    const c = animate(prev.current, value, { duration: reduced() ? 0 : 0.9, ease: EASE, onUpdate: (v) => { if (ref.current) ref.current.textContent = fmt(v) } })
    prev.current = value
    return () => c.stop()
  }, [value])
  return <span ref={ref} className={className}>{fmt(value)}</span>
}

/* ---------- Risk gauge: risk and confidence always together, drawn differently ---------- */

export function RiskGauge({ risk, lo, hi, confidence, source }: { risk: number; lo?: number; hi?: number; confidence: number; source: string }) {
  const b = band(risk)
  const segs = 20
  const filled = Math.round(confidence * segs)
  return (
    <div className="grid grid-cols-[1fr_auto] gap-x-5">
      <div>
        <div className="flex items-baseline gap-2">
          <span className="text-xs text-muted">Risk</span>
          <Prov source={source} detail="Model probability of fraud, 0–100."><Num value={risk * 100} className={cn('text-2xl font-semibold transition-colors duration-700', riskText[b])} /></Prov>
          <RiskChip risk={risk} />
        </div>
        <div className="relative mt-2 h-5" role="img" aria-label={`Risk ${pct(risk)} out of 100${lo !== undefined ? `, 90% interval ${pct(lo)} to ${pct(hi!)}` : ''}`}>
          <div className="absolute inset-x-0 top-2 flex h-1.5 overflow-hidden rounded-sm">
            <span className="w-[40%] bg-risk-low opacity-30" /><span className="w-[30%] bg-risk-med opacity-30" /><span className="w-[30%] bg-risk-high opacity-30" />
          </div>
          {lo !== undefined && hi !== undefined && (
            <motion.div
              className="hatch absolute inset-x-0 top-0 h-5 border-x border-conf"
              initial={false}
              animate={{ clipPath: `inset(0 ${100 - hi * 100}% 0 ${lo * 100}%)` }}
              transition={{ duration: 0.9, ease: EASE }}
              style={{ opacity: 0.55 }}
            />
          )}
          <motion.div className="absolute inset-x-0 top-0 h-5" initial={false} animate={{ x: `${risk * 100}%` }} transition={{ duration: 0.9, ease: EASE }}>
            <span className={cn('absolute -left-px top-0 h-5 w-[3px] rounded-sm transition-colors duration-700', riskBg[b])} />
          </motion.div>
        </div>
        <div className="mt-1 flex justify-between text-2xs text-faint"><span>0</span><span>40</span><span>70</span><span>100</span></div>
        <div className="text-xs text-muted">
          {lo !== undefined ? (
            <Prov source={`${source} riskLo/riskHi`} detail="Hatched band: 90% interval. Narrower means the evidence agrees.">90% interval <span className="text-conf"><Num value={lo * 100} />–<Num value={hi! * 100} /></span></Prov>
          ) : <span className="text-faint">No interval yet: agent has not run on this case</span>}
        </div>
      </div>
      <div className="w-28 border-l border-line pl-4">
        <div className="text-xs text-muted">Confidence</div>
        <Prov source={`${source} confidence`} detail="How sufficient the evidence is for the recommendation. Independent of risk."><Num value={confidence * 100} className="text-2xl font-semibold text-conf" /></Prov>
        <div className="mt-2 flex gap-px" role="img" aria-label={`Confidence ${pct(confidence)} out of 100`}>
          {Array.from({ length: segs }, (_, i) => (
            <span key={i} className={cn('h-3 flex-1 transition-colors duration-500', i < filled ? 'bg-conf' : 'bg-line')} style={{ transitionDelay: `${i * 20}ms` }} />
          ))}
        </div>
        <div className="mt-1 text-2xs text-faint">{confidence >= 0.75 ? 'Sufficient' : confidence >= 0.5 ? 'Partial' : 'Thin'} evidence</div>
      </div>
    </div>
  )
}

/* ---------- Uncertainty ---------- */

export function Uncertainty({ rec }: { rec: Recommendation }) {
  const max = Math.max(...rec.unknowns.map((u) => u.infoGain), 0.01)
  const sorted = [...rec.unknowns].sort((a, b) => Number(a.resolved) - Number(b.resolved) || b.infoGain - a.infoGain)
  return (
    <section aria-label="Uncertainty">
      <SectionHead aside={<span className="text-2xs text-faint">Expected info gain, bits</span>}>What is still unknown</SectionHead>
      <ul className="space-y-1.5">
        <AnimatePresence initial={false}>
          {sorted.map((u) => (
            <motion.li key={u.id} layout="position" transition={{ duration: 0.4, ease: EASE }} className={cn('grid grid-cols-[1fr_72px] gap-x-3 text-xs', u.resolved && 'opacity-55')}>
              <div>
                <div className={cn(u.resolved && 'line-through decoration-faint')}>{u.question}</div>
                <div className="text-2xs text-muted">{u.resolved ? 'Resolved by ' : 'Resolve with '}{u.resolvedBy}</div>
              </div>
              <div className="pt-0.5">
                <div className="flex items-baseline justify-between">
                  <Prov source={`${rec.id}.unknowns.${u.id}.infoGain`} detail="Expected reduction in entropy of the fraud/not-fraud outcome if this evidence is obtained.">{u.infoGain.toFixed(2)}</Prov>
                  {u.resolved && <span className="text-2xs text-muted">done</span>}
                </div>
                <div className="mt-1 h-1 bg-line"><motion.div className="h-1 origin-left bg-conf" initial={false} animate={{ scaleX: u.infoGain / max }} transition={{ duration: 0.6 }} /></div>
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </section>
  )
}

/* ---------- Recommendation card, before/after ---------- */

const ROUTE_HINT: Record<Recommendation['route'], string> = {
  auto_execute: 'Policy allows the agent to execute without a human.',
  analyst_approval: 'One analyst must approve.',
  dual_approval: 'Two approvers required: analyst plus MLRO delegate.',
}

export function RecCard({ rec, label, muted }: { rec: Recommendation; label?: string; muted?: boolean }) {
  const policies = usePolicies()
  const p = policies[rec.policyId]
  return (
    <motion.div
      layoutId={rec.id}
      transition={{ duration: 0.6, ease: EASE }}
      className={cn('rounded border bg-panel p-2.5', muted ? 'border-line' : 'border-line-strong')}
    >
      {label && <div className="flex items-baseline justify-between text-2xs text-muted"><span>{label}</span><span className="font-mono text-faint">{rec.id}</span></div>}
      <div className={cn('mt-0.5 font-semibold leading-5', muted ? 'text-sm text-muted line-through decoration-faint' : 'text-base')}>{rec.action}</div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <Tip content={ROUTE_HINT[rec.route]}><span tabIndex={0}><Tag className={cn(!muted && rec.route !== 'analyst_approval' && 'border-accent text-accent')}>{routeLabel(rec.route)}</Tag></span></Tip>
        <Prov source={p ? `${p.doc} §${p.clause} ${p.title}` : rec.policyId} detail={p?.text}><span className="text-2xs text-muted">{p ? `${p.doc} §${p.clause}` : rec.policyId}</span></Prov>
      </div>
      <div className="mt-1.5 flex items-baseline gap-2 text-xs">
        <span className={riskText[band(rec.risk)]}>Risk {pct(rec.risk)}</span>
        <span className="text-conf">{pct(rec.riskLo)}–{pct(rec.riskHi)}</span>
        <span className="text-muted">conf {pct(rec.confidence)}</span>
      </div>
    </motion.div>
  )
}

export function BeforeAfter({ prior, current, steps }: { prior: Recommendation; current: Recommendation; steps: AgentStep[] }) {
  const showNode = useStore((s) => s.showNode)
  const showStep = useStore((s) => s.showStep)
  const flipped = prior.action !== current.action
  const rows = diffRecs(prior, current)
  const evidence = current.causedBy.map((id) => ({ id, step: steps.find((s) => s.evidence?.id === id) }))
  const at = steps.find((s) => s.recommendation?.id === current.id)
  return (
    <motion.section
      aria-label="Recommendation change"
      aria-live="polite"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold">{flipped ? 'Recommendation changed' : 'Recommendation refined'}</h3>
        {at && <button onClick={() => showStep(at.id)} className="text-2xs text-accent hover:underline">at step {at.seq}, {at.at.slice(11, 19)}</button>}
      </div>
      <motion.div className="mt-1 h-px origin-left bg-accent" initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, ease: EASE, delay: 0.2 }} />

      <div className="relative mt-2 grid grid-cols-2 gap-2">
        <RecCard rec={prior} label="Before" muted />
        <motion.div initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, ease: EASE, delay: 0.35 }}>
          <RecCard rec={current} label="After" />
        </motion.div>
      </div>

      <table className="mt-2 w-full text-xs">
        <caption className="sr-only">Field-by-field difference</caption>
        <thead><tr className="text-left text-2xs text-faint"><th className="py-0.5 font-normal">Field</th><th className="font-normal">Before</th><th className="font-normal">After</th><th className="text-right font-normal">Δ</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <motion.tr
              key={r.field}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.7 + i * 0.07 }}
              className={cn('border-t border-line align-top', !r.changed && 'text-faint')}
            >
              <td className="py-1 pr-2 text-muted">{r.field}</td>
              <td className="py-1 pr-2">{r.before || <span className="text-faint">none</span>}</td>
              <td className={cn('py-1 pr-2', r.changed && 'font-medium')}>
                {r.changed ? (
                  <motion.span className="rounded-sm px-0.5" initial={{ backgroundColor: 'var(--accent-soft)' }} animate={{ backgroundColor: 'rgba(0,0,0,0)' }} transition={{ duration: 1.6, delay: 1 + i * 0.07 }}>{r.after}</motion.span>
                ) : r.after}
              </td>
              <td className="py-1 text-right">{r.delta !== undefined && r.delta !== 0 ? <Num value={r.delta} signed /> : ''}</td>
            </motion.tr>
          ))}
        </tbody>
      </table>

      <div className="mt-2">
        <div className="text-2xs text-muted">Caused by</div>
        <ul className="mt-1 space-y-1">
          {evidence.map(({ id, step }, i) => (
            <motion.li key={id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.2 + i * 0.1 }} className="flex items-baseline gap-2 text-xs">
              <Prov source={step?.evidence?.source ?? id} detail={step?.evidence?.summary}><span className="font-mono text-2xs">{id}</span></Prov>
              <span className="min-w-0 flex-1 truncate">{step?.evidence?.label ?? 'Evidence not yet visible at this replay position'}</span>
              {step?.evidence?.nodes[0] && <button className="shrink-0 text-2xs text-accent hover:underline" onClick={() => showNode(step.evidence!.nodes[0])}>Show in graph</button>}
            </motion.li>
          ))}
        </ul>
      </div>
    </motion.section>
  )
}

/* ---------- Actions with permissions, confirmation, optimistic audit ---------- */

const CLOSES = new Set(['block_card', 'freeze', 'recall', 'close_fp', 'file_sar'])

export function ActionBar({ c, rec }: { c: Case; rec: Recommendation }) {
  const policies = usePolicies()
  const qc = useQueryClient()
  const audit = useStore((s) => s.audit)
  const [pending, setPending] = useState<ActionOption | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = useMutation({
    mutationFn: (a: { option: ActionOption; tempId: string }) => api.executeAction(c.id, a.option.id, a.option.label),
    onMutate: async ({ option, tempId }) => {
      setError(null)
      await qc.cancelQueries({ queryKey: ['cases'] })
      const snapshot = qc.getQueryData<Case[]>(['cases'])
      if (CLOSES.has(option.id)) qc.setQueryData<Case[]>(['cases'], (cs) => cs?.map((x) => (x.id === c.id ? { ...x, status: 'closed', stateSince: new Date().toISOString() } : x)))
      useStore.getState().addAudit({ id: tempId, at: new Date().toISOString(), caseId: c.id, actionId: option.id, label: option.label, actor: 'analyst.jdoe', status: 'pending' })
      return { snapshot }
    },
    onSuccess: (entry, { tempId }) => useStore.getState().patchAudit(tempId, { status: 'committed', at: entry.at, actor: entry.actor }),
    onError: (err, { tempId }, ctx) => {
      if (ctx?.snapshot) qc.setQueryData(['cases'], ctx.snapshot)
      useStore.getState().patchAudit(tempId, { status: 'rolled_back', error: err.message })
      setError(`${err.message}. Case state was restored; try again.`)
    },
  })

  const done = (id: string) => audit.find((a) => a.caseId === c.id && a.actionId === id && a.status !== 'rolled_back')
  const policyName = (id: string) => { const p = policies[id]; return p ? `${p.doc} §${p.clause} ${p.title}` : id }

  return (
    <section aria-label="Actions">
      <SectionHead>Actions</SectionHead>
      <div className="flex flex-wrap gap-1.5">
        {rec.actions.map((a, i) => {
          const d = done(a.id)
          if (!a.allowed) {
            return (
              <Tip key={a.id} content={<><div className="font-medium">Blocked by {policyName(a.policyId)}</div>{a.reason && <div className="mt-0.5 text-muted">{a.reason}</div>}</>}>
                <span tabIndex={0} aria-label={`${a.label}, blocked by ${policyName(a.policyId)}`}><Button size="sm" disabled className="pointer-events-none">{a.label}</Button></span>
              </Tip>
            )
          }
          const primary = i === 0 // fixtures list the recommended action first
          return (
            <Button key={a.id} size="sm" variant={primary && !d ? 'primary' : 'outline'} disabled={!!d} onClick={() => setPending(a)}>
              {d ? `${a.label}: ${d.status === 'pending' ? 'sending' : 'done'}` : a.label}
            </Button>
          )
        })}
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-risk-high">{error}</p>}
      <Confirm
        open={!!pending}
        onOpenChange={(o) => !o && setPending(null)}
        title={pending ? `${pending.label} on ${c.id}?` : ''}
        confirmLabel={pending?.label ?? 'Confirm'}
        onConfirm={() => { if (pending) run.mutate({ option: pending, tempId: crypto.randomUUID() }); setPending(null) }}
        body={pending && (
          <div className="space-y-2">
            <p>Authorized by {policyName(pending.policyId)}. Route: {routeLabel(rec.route).toLowerCase()}. {ROUTE_HINT[rec.route]}</p>
            <p>This is written to the audit trail with your analyst ID and the recommendation {rec.id}.</p>
          </div>
        )}
      />
    </section>
  )
}

export function AuditTrail({ entries }: { entries: AuditEntry[] }) {
  return (
    <section aria-label="Audit trail">
      <SectionHead>Audit trail</SectionHead>
      {entries.length === 0 ? <p className="text-xs text-faint">No analyst actions on this case yet.</p> : (
        <ol className="space-y-1">
          {entries.map((e) => (
            <li key={e.id} className="grid grid-cols-[56px_1fr_auto] gap-2 text-xs">
              <span className="text-faint">{e.at.slice(11, 19)}</span>
              <span className={cn(e.status === 'rolled_back' && 'text-muted line-through')}>{e.label} <span className="text-muted">by {e.actor}</span>{e.error && <span className="block text-2xs text-risk-high no-underline">{e.error}</span>}</span>
              <span className={cn('text-2xs', e.status === 'pending' ? 'text-accent' : 'text-muted')}>{e.status === 'rolled_back' ? 'Rolled back' : e.status === 'pending' ? 'Sending' : 'Committed'}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export function SimilarCases({ items }: { items: SimilarCase[] }) {
  const OUT = { confirmed_fraud: 'Confirmed fraud', false_positive: 'False positive', inconclusive: 'Inconclusive' }
  return (
    <section aria-label="Similar past cases">
      <SectionHead aside={<span className="text-2xs text-faint">GraphRAG retrieval</span>}>Similar past cases</SectionHead>
      <ul className="space-y-2">
        {items.map((s) => (
          <li key={s.caseId} className="border-l-2 border-line-strong pl-2 text-xs">
            <div className="flex items-baseline gap-2">
              <span className="font-medium">{s.caseId}</span>
              <Prov source="GraphRAG: cosine over case embeddings, re-ranked by 2-hop structural overlap">{pct(s.similarity)}% similar</Prov>
              <span className="ml-auto text-muted">{OUT[s.outcome]}</span>
            </div>
            <div className="text-muted">Decided: {s.decision}</div>
            <blockquote className="mt-0.5 text-fg">“{s.analystNote}”</blockquote>
          </li>
        ))}
      </ul>
    </section>
  )
}

/* ---------- Panel ---------- */

export function DecisionPanel({ view }: { view: CaseView }) {
  const { c, inv, current, prior, steps, status, streaming } = view
  const audit = useStore((s) => s.audit)
  const cursor = useStore((s) => s.cursor)

  if (!c) {
    return <aside aria-label="Decision panel" className="border-l border-line bg-panel p-4 text-sm text-muted">Select a case to see the agent's recommendation.</aside>
  }
  const src = current ? `recommendation ${current.id}` : `case ${c.id} (queue score)`

  return (
    <aside aria-label="Decision panel" className="flex min-h-0 flex-col border-l border-line bg-panel">
      <header className="flex items-baseline gap-2 border-b border-line px-4 py-2">
        <h2 className="text-sm font-semibold">Decision</h2>
        <span className="text-xs text-muted">{status && STATUS[status]}</span>
        <span className="ml-auto text-2xs text-faint">{cursor !== null ? `Replay, step ${cursor} of ${view.allSteps.length}` : streaming ? 'Live, agent running' : c.hasRun ? 'Live' : 'No agent run'}</span>
      </header>
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-3">
        {current ? (
          <RiskGauge risk={current.risk} lo={current.riskLo} hi={current.riskHi} confidence={current.confidence} source={src} />
        ) : c.hasRun ? (
          <div className="space-y-2" aria-label="Waiting for first recommendation">
            <Skeleton className="h-7 w-32" /><Skeleton className="h-5 w-full" /><Skeleton className="w-40" />
            <p className="text-xs text-muted">Agent is gathering evidence ({steps.length} step{steps.length === 1 ? '' : 's'} so far). Risk and confidence appear with the first recommendation.</p>
          </div>
        ) : (
          <>
            <RiskGauge risk={c.risk} confidence={c.confidence} source={src} />
            <p className="text-xs text-muted">This benchmark case has no agent run in the mock data. Full runs: FC-1041, FC-1042, FC-1043.</p>
          </>
        )}

        <LayoutGroup>
          {current && (prior ? (
            <BeforeAfter key={current.id} prior={prior} current={current} steps={steps} />
          ) : (
            <section aria-label="Next best action">
              <SectionHead>Next best action</SectionHead>
              <RecCard rec={current} />
            </section>
          ))}
        </LayoutGroup>

        {current && (
          <>
            <p className="max-w-[60ch] text-xs text-muted">{current.rationale}</p>
            {inv && <ActionBar c={c} rec={current} />}
            <Uncertainty rec={current} />
          </>
        )}
        {!current && c.hasRun && <div className="space-y-2"><Skeleton className="h-16 w-full" /><Skeleton className="h-10 w-full" /></div>}

        <AuditTrail entries={audit.filter((a) => a.caseId === c.id)} />
        {inv ? <SimilarCases items={inv.similar} /> : c.hasRun && <Skeleton className="h-24 w-full" />}
      </div>
    </aside>
  )
}
