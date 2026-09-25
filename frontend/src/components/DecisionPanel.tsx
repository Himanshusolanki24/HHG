import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, LayoutGroup, animate, motion } from 'motion/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { CaseView } from '../hooks.ts'
import { usePolicies } from '../hooks.ts'
import { useStore } from '../store.ts'
import { api } from '../api/client.ts'
import { PATTERN_LABEL, ROUTE_LABEL, band, diffRecs, rule } from '../derive.ts'
import type { Action, AgentStep, Answer, AuditEntry, Case, Recommendation, SimilarCase } from '../api/schemas.ts'
import { STATUS } from './CaseQueue.tsx'
import { Button, Confirm, Prov, RiskChip, SectionHead, Skeleton, Tag, Tip, cn, riskBg, riskText } from './ui.tsx'

const pct = (n: number) => (n * 100).toFixed(0)
const money = (n: number) => `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const EASE = [0.2, 0.7, 0.2, 1] as const
const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches

/** Tweens a number in place (transform-free text update, no re-render per frame). */
export function Num({ value, className, signed }: { value: number; className?: string; signed?: boolean }) {
  const ref = useRef<HTMLSpanElement>(null)
  const prev = useRef(value)
  useEffect(() => {
    const fmt = (v: number) => `${signed && v > 0 ? '+' : ''}${Math.round(v)}`
    const c = animate(prev.current, value, { duration: reduced() ? 0 : 0.9, ease: EASE, onUpdate: (v) => { if (ref.current) ref.current.textContent = fmt(v) } })
    prev.current = value
    return () => c.stop()
  }, [value, signed])
  return <span ref={ref} className={className}>{`${signed && value > 0 ? '+' : ''}${Math.round(value)}`}</span>
}

/* ---------- Gauge: fraud probability and confidence always together, drawn differently ---------- */

export function RiskGauge({ risk, lo, hi, confidence, source, modelScore }: {
  risk: number; lo?: number; hi?: number; confidence: number; source: string; modelScore?: number | null
}) {
  const b = band(risk)
  const segs = 20
  const filled = Math.round(confidence * segs)
  return (
    <div className="grid grid-cols-[1fr_auto] gap-x-5">
      <div>
        <div className="flex items-baseline gap-2">
          <span className="text-xs text-muted">Fraud probability</span>
          <Prov source={source} detail="The agent's assessed probability that the flagged activity is fraud, from graph evidence and case memory."><Num value={risk * 100} className={cn('text-2xl font-semibold transition-colors duration-700', riskText[b])} /></Prov>
          <RiskChip risk={risk} />
        </div>
        <div className="relative mt-2 h-5" role="img" aria-label={`Fraud probability ${pct(risk)} out of 100${lo !== undefined ? `, 90% band ${pct(lo)} to ${pct(hi!)}` : ''}`}>
          <div className="absolute inset-x-0 top-2 flex h-1.5 overflow-hidden rounded-sm">
            <span className="w-[30%] bg-risk-low opacity-30" /><span className="w-[40%] bg-risk-med opacity-30" /><span className="w-[30%] bg-risk-high opacity-30" />
          </div>
          {lo !== undefined && hi !== undefined && (
            <motion.div className="hatch absolute inset-x-0 top-0 h-5 border-x border-conf" initial={false}
              animate={{ clipPath: `inset(0 ${100 - hi * 100}% 0 ${lo * 100}%)` }} transition={{ duration: 0.9, ease: EASE }} style={{ opacity: 0.55 }} />
          )}
          <motion.div className="absolute inset-x-0 top-0 h-5" initial={false} animate={{ x: `${risk * 100}%` }} transition={{ duration: 0.9, ease: EASE }}>
            <span className={cn('absolute -left-px top-0 h-5 w-[3px] rounded-sm transition-colors duration-700', riskBg[b])} />
          </motion.div>
          {modelScore != null && (
            <Tip content={`Bank model score ${modelScore.toFixed(2)}: an input that started the alert, not evidence. Above 0.7 most alerts are legitimate (dataset README).`}>
              <span tabIndex={0} className="absolute top-0 h-5 w-0 border-l border-dashed border-muted" style={{ left: `${modelScore * 100}%` }} aria-label={`Model score ${modelScore.toFixed(2)}`} />
            </Tip>
          )}
        </div>
        <div className="mt-1 flex justify-between text-2xs text-faint"><span>0</span><span>30</span><span>70</span><span>100</span></div>
        <div className="flex flex-wrap gap-x-3 text-xs text-muted">
          {lo !== undefined && <Prov source={`${source} pLo/pHi`} detail="Hatched: 90% band. Narrower when more independent evidence agrees.">90% band <span className="text-conf"><Num value={lo * 100} />–<Num value={hi! * 100} /></span></Prov>}
          {modelScore != null && <span>Model score {modelScore.toFixed(2)} <span className="text-faint">(dashed, input only)</span></span>}
        </div>
      </div>
      <div className="w-28 border-l border-line pl-4">
        <div className="text-xs text-muted">Confidence</div>
        <Prov source={`${source}: 1 − band width`} detail="How tightly the evidence pins the probability. Independent of the probability itself."><Num value={confidence * 100} className="text-2xl font-semibold text-conf" /></Prov>
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

/* ---------- Uncertainty: which permitted request would teach us most ---------- */

export function Uncertainty({ rec }: { rec: Recommendation }) {
  const max = Math.max(...rec.unknowns.map((u) => u.infoGain), 0.01)
  const sorted = [...rec.unknowns].sort((a, b) => Number(a.resolved) - Number(b.resolved) || b.infoGain - a.infoGain)
  return (
    <section aria-label="Uncertainty">
      <SectionHead aside={<span className="text-2xs text-faint">Expected information gain, bits</span>}>What would settle it</SectionHead>
      <ul className="space-y-1.5">
        <AnimatePresence initial={false}>
          {sorted.map((u) => (
            <motion.li key={u.id} layout="position" transition={{ duration: 0.4, ease: EASE }} className={cn('grid grid-cols-[1fr_72px] gap-x-3 text-xs', u.resolved && 'opacity-55')}>
              <div>
                <div className={cn(u.resolved && 'line-through decoration-faint')}>{u.question}</div>
                <div className="text-2xs text-muted">{u.resolved ? 'Asked; reply received' : u.id.replaceAll('_', ' ')}</div>
              </div>
              <div className="pt-0.5">
                <Prov source={`${rec.id}.unknowns.${u.id}.infoGain`} detail="Entropy of fraud/not-fraud now, minus the expected entropy after the reply, using the reply model in agent.py.">{u.infoGain.toFixed(2)}</Prov>
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

export function ActionLine({ a, muted }: { a: Action; muted?: boolean }) {
  const policies = usePolicies()
  const p = policies[rule(a)]
  return (
    <li className="flex flex-wrap items-baseline gap-x-1.5 text-xs">
      <span className={cn('min-w-0 font-medium break-all', muted && 'text-muted')}>{a.action}</span>
      <Tag className={cn(a.route !== 'auto' && !muted && 'border-accent text-accent')}>{a.route}</Tag>
      <Prov source={p ? `${p.doc}, ${p.clause}: ${p.title}` : rule(a)} detail={a.reason}><span className="text-2xs text-muted">{rule(a)}</span></Prov>
    </li>
  )
}

export function RecCard({ rec, label, muted }: { rec: Recommendation; label?: string; muted?: boolean }) {
  return (
    <motion.div layoutId={rec.id} transition={{ duration: 0.6, ease: EASE }} className={cn('rounded border bg-panel p-2.5', muted ? 'border-line' : 'border-line-strong')}>
      {label && <div className="flex items-baseline justify-between text-2xs text-muted"><span>{label}</span><span className="font-mono text-faint">{rec.stage}</span></div>}
      <div className={cn('mt-0.5 flex items-baseline gap-2', muted && 'text-muted')}>
        <span className="text-base font-semibold capitalize">{rec.verdict}</span>
        <span className={cn('text-xs', riskText[band(rec.p)])}>{pct(rec.p)}</span>
        <span className="text-xs text-conf">{pct(rec.pLo)}–{pct(rec.pHi)}</span>
      </div>
      <div className="text-2xs text-muted">{PATTERN_LABEL[rec.pattern]}</div>
      <ul className="mt-1.5 space-y-0.5">{rec.actions.map((a) => <ActionLine key={a.action} a={a} muted={muted} />)}</ul>
    </motion.div>
  )
}

export function BeforeAfter({ prior, current, steps, whatChanged }: { prior: Recommendation; current: Recommendation; steps: AgentStep[]; whatChanged?: string }) {
  const showNode = useStore((s) => s.showNode)
  const showStep = useStore((s) => s.showStep)
  const flipped = prior.verdict !== current.verdict || prior.actions.map((a) => a.action).join() !== current.actions.map((a) => a.action).join()
  const rows = diffRecs(prior, current)
  const evidence = current.causedBy.map((id) => ({ id, step: steps.find((s) => s.evidence?.id === id) }))
  const at = steps.find((s) => s.recommendation?.id === current.id)
  return (
    <motion.section aria-label="Recommendation change" aria-live="polite" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold">{flipped ? 'Recommendation changed after the reply' : 'Recommendation confirmed by the reply'}</h3>
        {at && <button onClick={() => showStep(at.id)} className="text-2xs text-accent hover:underline">step {at.seq}</button>}
      </div>
      <motion.div className="mt-1 h-px origin-left bg-accent" initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.8, ease: EASE, delay: 0.2 }} />

      <div className="relative mt-2 grid grid-cols-2 gap-2">
        <RecCard rec={prior} label="Before evidence" muted />
        <motion.div initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, ease: EASE, delay: 0.35 }}>
          <RecCard rec={current} label="After evidence" />
        </motion.div>
      </div>

      <table className="mt-2 w-full text-xs">
        <caption className="sr-only">Field-by-field difference</caption>
        <thead><tr className="text-left text-2xs text-faint"><th className="py-0.5 font-normal">Field</th><th className="font-normal">Before</th><th className="font-normal">After</th><th className="text-right font-normal">Δ</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <motion.tr key={r.field} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.7 + i * 0.07 }}
              className={cn('border-t border-line align-top', !r.changed && 'text-faint')}>
              <td className="py-1 pr-2 text-muted">{r.field}</td>
              <td className="py-1 pr-2 break-words">{r.before}</td>
              <td className={cn('py-1 pr-2 break-words', r.changed && 'font-medium')}>
                {r.changed ? (
                  <motion.span className="rounded-sm px-0.5" initial={{ backgroundColor: 'var(--accent-soft)' }} animate={{ backgroundColor: 'rgba(0,0,0,0)' }} transition={{ duration: 1.6, delay: 1 + i * 0.07 }}>{r.after}</motion.span>
                ) : r.after}
              </td>
              <td className="py-1 text-right">{r.delta !== undefined && r.delta !== 0 ? <Num value={r.delta} signed /> : ''}</td>
            </motion.tr>
          ))}
        </tbody>
      </table>

      {whatChanged && <p className="mt-2 max-w-[60ch] text-xs text-muted">{whatChanged}</p>}
      <div className="mt-2">
        <div className="text-2xs text-muted">Caused by</div>
        <ul className="mt-1 space-y-1">
          {evidence.map(({ id, step }, i) => (
            <motion.li key={id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.2 + i * 0.1 }} className="flex items-baseline gap-2 text-xs">
              <Prov source={step?.evidence?.source ?? id} detail={step?.evidence?.summary}><span className="font-mono text-2xs">{id}</span></Prov>
              <span className="min-w-0 flex-1 truncate">{step?.evidence?.summary ?? 'Not yet visible at this replay position'}</span>
              {step?.evidence?.nodes[0] && <button className="shrink-0 text-2xs text-accent hover:underline" onClick={() => showNode(step.evidence!.nodes[0])}>Show in graph</button>}
            </motion.li>
          ))}
        </ul>
      </div>
    </motion.section>
  )
}

/* ---------- Actions with permissions, confirmation, optimistic audit ---------- */

const APPROVER: Record<Action['route'], string> = { auto: 'the agent', L1: 'a team lead (L1)', L2: 'a fraud manager (L2)' }
const CLOSES = new Set(['CLOSE_NO_FRAUD', 'BLOCK_CARD', 'BLOCK_ALL_CARDS'])

export function ActionBar({ c, rec }: { c: Case; rec: Recommendation }) {
  const qc = useQueryClient()
  const audit = useStore((s) => s.audit)
  const [pending, setPending] = useState<Action | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = useMutation({
    mutationFn: (a: { action: Action; tempId: string }) => api.executeAction(c.id, a.action.action, a.action.action),
    onMutate: async ({ action, tempId }) => {
      setError(null)
      await qc.cancelQueries({ queryKey: ['cases'] })
      const snapshot = qc.getQueryData<Case[]>(['cases'])
      if (CLOSES.has(action.action)) qc.setQueryData<Case[]>(['cases'], (cs) => cs?.map((x) => (x.id === c.id ? { ...x, status: 'closed', stateSince: new Date().toISOString() } : x)))
      useStore.getState().addAudit({ id: tempId, at: new Date().toISOString(), caseId: c.id, actionId: action.action, label: action.action, actor: 'analyst.jdoe', status: 'pending' })
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

  return (
    <section aria-label="Actions">
      <SectionHead aside={<span className="text-2xs text-faint">Policy §2: only auto actions run without a person</span>}>Next best action</SectionHead>
      <div className="flex flex-wrap gap-1.5">
        {rec.actions.map((a, i) => {
          const d = done(a.action)
          if (a.route !== 'auto') {
            return (
              <Tip key={a.action} content={<><div className="font-medium">Needs {APPROVER[a.route]} under policy §2</div><div className="mt-0.5 text-muted">{a.reason}</div></>}>
                <span tabIndex={0} aria-label={`${a.action}, needs ${APPROVER[a.route]}`}><Button size="sm" disabled className="pointer-events-none">{a.action} <span className="text-2xs">{a.route}</span></Button></span>
              </Tip>
            )
          }
          return (
            <Tip key={a.action} content={a.reason}>
              <Button size="sm" variant={i === 0 && !d ? 'primary' : 'outline'} disabled={!!d} onClick={() => setPending(a)}>
                {d ? `${a.action}: ${d.status === 'pending' ? 'sending' : 'done'}` : a.action}
              </Button>
            </Tip>
          )
        })}
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-risk-high">{error}</p>}
      <Confirm
        open={!!pending}
        onOpenChange={(o) => !o && setPending(null)}
        title={pending ? `Run ${pending.action} on ${c.id}?` : ''}
        confirmLabel={pending ? `Run ${pending.action}` : 'Run'}
        onConfirm={() => { if (pending) run.mutate({ action: pending, tempId: crypto.randomUUID() }); setPending(null) }}
        body={pending && (
          <div className="space-y-2">
            <p>{pending.reason}. Route: {ROUTE_LABEL[pending.route].toLowerCase()}, so the agent may run it without approval.</p>
            <p>This is written to the audit trail with your analyst ID and recommendation {rec.id}.</p>
          </div>
        )}
      />
    </section>
  )
}

export function SarBlock({ sar }: { sar: Answer['sar'] }) {
  return (
    <section aria-label="Suspicious activity report">
      <SectionHead aside={<Tag className={cn(sar.file && 'border-accent text-accent')}>{sar.file ? 'File, L2' : 'Not required'}</Tag>}>Suspicious activity report</SectionHead>
      <p className="text-xs text-muted">{sar.reason}</p>
      {sar.file && (
        <details className="mt-1.5 text-xs">
          <summary className="text-accent">Read the narrative ({money(sar.total_amount_usd)}, {sar.activity_dates.join(' to ')})</summary>
          <p className="mt-1.5 max-w-[65ch] leading-5">{sar.narrative}</p>
          <p className="mt-1 text-2xs text-faint">Subjects: {sar.subjects.join(', ')}</p>
        </details>
      )}
    </section>
  )
}

export function AuditTrail({ entries }: { entries: AuditEntry[] }) {
  return (
    <section aria-label="Audit trail">
      <SectionHead>Audit trail</SectionHead>
      {entries.length === 0 ? <p className="text-xs text-faint">No actions run on this case yet.</p> : (
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
  const OUT = { confirmed_fraud: 'Confirmed fraud', false_positive: 'Cleared', inconclusive: 'This run' }
  return (
    <section aria-label="Similar past cases">
      <SectionHead aside={<span className="text-2xs text-faint">Case memory</span>}>Similar past cases</SectionHead>
      {items.length === 0 && <p className="text-xs text-faint">No similar closed cases found.</p>}
      <ul className="space-y-2">
        {items.map((s) => (
          <li key={s.caseId} className="border-l-2 border-line-strong pl-2 text-xs">
            <div className="flex items-baseline gap-2">
              <span className="font-medium">{s.caseId}</span>
              <Prov source="Case memory: same card, shared device, or same typology nearest in exposure (agent.similar_cases)">{pct(s.similarity)}% similar</Prov>
              <span className="ml-auto text-muted">{OUT[s.outcome]}</span>
            </div>
            <div className="text-muted">Decided: {s.decision}</div>
            {s.analystNote && <blockquote className="mt-0.5 text-fg">“{s.analystNote}”</blockquote>}
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
  const src = current ? `recommendation ${current.id}` : `case ${c.id}`
  const settled = current && (current.stage === 'final' || !inv?.answer.evidence_requests.length)

  return (
    <aside aria-label="Decision panel" className="flex min-h-0 flex-col border-l border-line bg-panel">
      <header className="flex items-baseline gap-2 border-b border-line px-4 py-2">
        <h2 className="text-sm font-semibold">Decision</h2>
        <span className="text-xs text-muted">{status && STATUS[status]}</span>
        <span className="ml-auto text-2xs text-faint">{cursor !== null ? `Replay, step ${cursor} of ${view.allSteps.length}` : streaming ? 'Live, agent running' : 'Live'}</span>
      </header>
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-3">
        {current ? (
          <RiskGauge risk={current.p} lo={current.pLo} hi={current.pHi} confidence={1 - (current.pHi - current.pLo)} source={src} modelScore={c.modelScore} />
        ) : (
          <div className="space-y-2" aria-label="Waiting for first recommendation">
            <Skeleton className="h-7 w-32" /><Skeleton className="h-5 w-full" /><Skeleton className="w-40" />
            <p className="text-xs text-muted">The agent is gathering evidence ({steps.length} step{steps.length === 1 ? '' : 's'} so far). Probability and confidence appear with the first recommendation.</p>
          </div>
        )}

        <LayoutGroup>
          {current && (prior ? (
            <BeforeAfter key={current.id} prior={prior} current={current} steps={steps} whatChanged={inv?.answer.next_best_actions.what_changed} />
          ) : (
            <section aria-label="Recommendation">
              <SectionHead>{inv?.answer.evidence_requests.length ? 'Before evidence' : 'Recommendation'}</SectionHead>
              <RecCard rec={current} />
            </section>
          ))}
        </LayoutGroup>

        {current && inv && <ActionBar c={c} rec={current} />}
        {settled && inv && <SarBlock sar={inv.answer.sar} />}
        {current && <Uncertainty rec={current} />}
        {!current && <div className="space-y-2"><Skeleton className="h-16 w-full" /><Skeleton className="h-10 w-full" /></div>}

        <AuditTrail entries={audit.filter((a) => a.caseId === c.id)} />
        {inv ? <SimilarCases items={inv.similar} /> : <Skeleton className="h-24 w-full" />}
      </div>
    </aside>
  )
}
