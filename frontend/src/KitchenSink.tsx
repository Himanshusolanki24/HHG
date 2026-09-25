import { useState } from 'react'
import { fixtures } from './api/mock.ts'
import { recommendations } from './derive.ts'
import { TopBar } from './App.tsx'
import { Button, Confirm, Prov, RiskChip, Skeleton, Tag, Tip } from './components/ui.tsx'
import { ActionBar, AuditTrail, BeforeAfter, RecCard, RiskGauge, SarBlock, SimilarCases, Uncertainty } from './components/DecisionPanel.tsx'
import { ClaimLink } from './components/AgentTrace.tsx'
import { Legend } from './components/GraphView.tsx'
import type { AuditEntry } from './api/schemas.ts'

// HHG-014: the shared-device ring. It has a before/after change, a report and connected cards, so it exercises everything.
const inv = fixtures.investigations['HHG-014']
const c = fixtures.cases.find((x) => x.id === 'HHG-014')!
const { prior, current } = recommendations(inv.steps)
const audit: AuditEntry[] = [
  { id: 'a2', at: '2016-11-22T20:40:12Z', caseId: c.id, actionId: 'MONITOR_CONNECTED_CARDS', label: 'MONITOR_CONNECTED_CARDS', actor: 'analyst.jdoe', status: 'committed' },
  { id: 'a1', at: '2016-11-22T20:39:02Z', caseId: c.id, actionId: 'CREATE_CASE', label: 'CREATE_CASE', actor: 'analyst.jdoe', status: 'rolled_back', error: 'Write conflict on InvestigationCase HHG-014' },
]

function Spec({ name, use, children }: { name: string; use: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-b border-line py-5 lg:grid-cols-[260px_1fr]">
      <div>
        <h2 className="font-mono text-sm">{name}</h2>
        <p className="mt-1 max-w-[40ch] text-xs text-muted">{use}</p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  )
}

export default function KitchenSink() {
  const [risk, setRisk] = useState(0.52)
  const [flip, setFlip] = useState(0)
  const [open, setOpen] = useState(false)
  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl px-4 pb-16">
          <div className="py-5">
            <h1 className="text-xl font-semibold">Component library</h1>
            <p className="text-sm text-muted">Every console component, rendered from the agent's real run on HHG-014. <a className="text-accent hover:underline" href="/">Back to the console</a></p>
          </div>

          <Spec name="Tokens" use="Slate base, one accent for interactive elements, risk colours only for risk. Confidence uses neutral ink.">
            <div className="flex flex-wrap gap-3 text-2xs">
              {['bg', 'panel', 'raised', 'line', 'line-strong', 'fg', 'muted', 'faint', 'accent', 'conf', 'risk-low', 'risk-med', 'risk-high'].map((t) => (
                <div key={t} className="w-20"><div className="h-8 rounded-sm border border-line" style={{ background: `var(--${t})` }} /><div className="mt-1 font-mono">--{t}</div></div>
              ))}
            </div>
          </Spec>

          <Spec name="Button" use="primary for the recommended action, outline for other allowed actions, ghost for view controls. Disabled buttons need a Tip naming the blocking policy.">
            <div className="flex flex-wrap gap-2"><Button variant="primary">CREATE_CASE</Button><Button>VERIFY_WITH_CUSTOMER</Button><Button variant="ghost">Collapse all</Button><Button disabled>BLOCK_CARD L1</Button><Button size="sm">Small</Button></div>
          </Spec>

          <Spec name="RiskChip, Tag" use="RiskChip is the only filled use of risk colours. Tag labels tools and routes.">
            <div className="flex flex-wrap items-center gap-3"><RiskChip risk={0.2} /><RiskChip risk={0.55} /><RiskChip risk={0.9} /><Tag>GSQL query</Tag><Tag>L2</Tag></div>
          </Spec>

          <Spec name="Prov, Tip" use="Wrap any number or claim in Prov with its source. It is focusable, so keyboard users get the same tooltip.">
            <p className="text-sm">Fraud probability <Prov source="recommendation R-HHG-014-final" detail="The agent's assessed probability.">98</Prov>, device used by <Prov source="GSQL device_txns, 30-day window">27 other cards</Prov>. <Tip content="Plain tooltip"><button className="text-accent">Hover me</button></Tip></p>
          </Spec>

          <Spec name="ClaimLink" use="Agent claims resolve to a graph node (click to focus), a policy clause, or an evidence item (hover for source).">
            <ul className="space-y-1 text-xs">{inv.steps.flatMap((st) => st.claims).slice(0, 6).map((cl, i) => <li key={i}><ClaimLink claim={cl} evidence={Object.fromEntries(inv.steps.flatMap((st) => (st.evidence ? [[st.evidence.id, st.evidence]] : [])))} /></li>)}</ul>
          </Spec>

          <Spec name="Skeleton" use="Shown per region while the agent streams. Never a whole-page spinner.">
            <div className="max-w-sm space-y-2"><Skeleton className="w-32" /><Skeleton className="h-5 w-full" /><Skeleton className="w-48" /></div>
          </Spec>

          <Spec name="RiskGauge" use="Risk (continuous bar, risk colour) and confidence (segmented, neutral) always render together. Hatched band is the 90% interval. Drag to see the tween.">
            <div className="max-w-md space-y-3">
              <RiskGauge risk={risk} lo={Math.max(0, risk - 0.1)} hi={Math.min(1, risk + 0.06)} confidence={0.84} source="kitchen-sink slider" modelScore={0.87} />
              <input type="range" min={0} max={100} value={risk * 100} onChange={(e) => setRisk(+e.target.value / 100)} aria-label="Demo risk" className="w-full accent-[var(--accent)]" />
            </div>
          </Spec>

          <Spec name="RecCard" use="Compact recommendation: action, approval route, cited policy clause, risk, interval, confidence.">
            <div className="grid max-w-lg grid-cols-2 gap-2">{prior && <RecCard rec={prior} label="Before" muted />}{current && <RecCard rec={current} label="After" />}</div>
          </Spec>

          <Spec name="BeforeAfter" use="The centrepiece. Prior card moves aside, the new one slides in, the diff rows stagger in with changes flashed, and the evidence that caused the change is listed with sources.">
            <div className="max-w-md">
              <Button size="sm" onClick={() => setFlip((n) => n + 1)}>Replay transition</Button>
              <div className="mt-3">{prior && current && <BeforeAfter key={flip} prior={prior} current={current} steps={inv.steps} whatChanged={inv.answer.next_best_actions.what_changed} />}</div>
            </div>
          </Spec>

          <Spec name="Uncertainty" use="Open questions ordered by expected information gain, with the evidence that would resolve each. Resolved ones sink and strike through.">
            <div className="max-w-md">{current && <Uncertainty rec={flip % 2 ? prior! : current} />}</div>
          </Spec>

          <Spec name="ActionBar" use="Allowed actions live; restricted ones disabled with a tooltip naming the policy. Each asks for confirmation, then writes optimistically to the audit trail and rolls back on error.">
            <div className="max-w-md">{current && <ActionBar c={c} rec={current} />}</div>
          </Spec>

          <Spec name="SarBlock" use="Whether policy 3a requires a suspicious activity report, why, and the narrative a regulator would read.">
            <div className="max-w-md"><SarBlock sar={inv.answer.sar} /></div>
          </Spec>

          <Spec name="AuditTrail" use="Pending, committed and rolled-back entries.">
            <div className="max-w-md"><AuditTrail entries={audit} /></div>
          </Spec>

          <Spec name="SimilarCases" use="GraphRAG-retrieved precedent with what the analyst decided then.">
            <div className="max-w-md"><SimilarCases items={inv.similar} /></div>
          </Spec>

          <Spec name="Legend" use="Graph legend: shape and fill encode entity type, border encodes risk.">
            <div className="relative h-20"><Legend className="bottom-auto top-0" /></div>
          </Spec>

          <Spec name="Confirm" use="Alert dialog used before every action execution.">
            <Button onClick={() => setOpen(true)}>Open confirm</Button>
            <Confirm open={open} onOpenChange={setOpen} title="Run MONITOR_CONNECTED_CARDS on HHG-014?" confirmLabel="Run MONITOR_CONNECTED_CARDS" onConfirm={() => {}} body="R6: 27 connected cards share the origin. Route auto. Written to the audit trail." />
          </Spec>
        </div>
      </div>
    </div>
  )
}
