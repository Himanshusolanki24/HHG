import { useState } from 'react'
import { fixtures } from './api/mock.ts'
import { recommendations } from './derive.ts'
import { TopBar } from './App.tsx'
import { Button, Confirm, Prov, RiskChip, Skeleton, Tag, Tip } from './components/ui.tsx'
import { ActionBar, AuditTrail, BeforeAfter, RecCard, RiskGauge, SimilarCases, Uncertainty } from './components/DecisionPanel.tsx'
import { ClaimLink } from './components/AgentTrace.tsx'
import { Legend } from './components/GraphView.tsx'
import type { AuditEntry } from './api/schemas.ts'

const inv = fixtures.investigations['FC-1042']
const c = fixtures.cases.find((x) => x.id === 'FC-1042')!
const { prior, current } = recommendations(inv.steps)
const audit: AuditEntry[] = [
  { id: 'a2', at: '2026-09-24T08:16:40Z', caseId: c.id, actionId: 'freeze', label: 'Freeze account', actor: 'analyst.jdoe', status: 'committed' },
  { id: 'a1', at: '2026-09-24T08:16:02Z', caseId: c.id, actionId: 'file_sar', label: 'File SAR', actor: 'analyst.jdoe', status: 'rolled_back', error: 'Write conflict on FraudCase FC-1042' },
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
            <p className="text-sm text-muted">Every console component, rendered from fixture FC-1042. <a className="text-accent hover:underline" href="/">Back to the console</a></p>
          </div>

          <Spec name="Tokens" use="Slate base, one accent for interactive elements, risk colours only for risk. Confidence uses neutral ink.">
            <div className="flex flex-wrap gap-3 text-2xs">
              {['bg', 'panel', 'raised', 'line', 'line-strong', 'fg', 'muted', 'faint', 'accent', 'conf', 'risk-low', 'risk-med', 'risk-high'].map((t) => (
                <div key={t} className="w-20"><div className="h-8 rounded-sm border border-line" style={{ background: `var(--${t})` }} /><div className="mt-1 font-mono">--{t}</div></div>
              ))}
            </div>
          </Spec>

          <Spec name="Button" use="primary for the recommended action, outline for other allowed actions, ghost for view controls. Disabled buttons need a Tip naming the blocking policy.">
            <div className="flex flex-wrap gap-2"><Button variant="primary">Freeze account</Button><Button>Require step-up auth</Button><Button variant="ghost">Collapse all</Button><Button disabled>Close as false positive</Button><Button size="sm">Small</Button></div>
          </Spec>

          <Spec name="RiskChip, Tag" use="RiskChip is the only filled use of risk colours. Tag labels tools and routes.">
            <div className="flex flex-wrap items-center gap-3"><RiskChip risk={0.2} /><RiskChip risk={0.55} /><RiskChip risk={0.9} /><Tag>GSQL query</Tag><Tag>Dual approval</Tag></div>
          </Spec>

          <Spec name="Prov, Tip" use="Wrap any number or claim in Prov with its source. It is focusable, so keyboard users get the same tooltip.">
            <p className="text-sm">Risk <Prov source="recommendation R-1042-2" detail="Model probability of fraud.">89</Prov>, 4 of 6 senders <Prov source="GraphRAG over customer_reports index, 4 docs">reported scams</Prov>. <Tip content="Plain tooltip"><button className="text-accent">Hover me</button></Tip></p>
          </Spec>

          <Spec name="ClaimLink" use="Agent claims resolve to a graph node (click to focus), a policy clause, or an evidence item (hover for source).">
            <ul className="space-y-1 text-xs">{inv.steps[10].claims.concat(inv.steps[6].claims).map((cl, i) => <li key={i}><ClaimLink claim={cl} evidence={{ 'EV-1042-3': inv.steps[7].evidence! }} /></li>)}</ul>
          </Spec>

          <Spec name="Skeleton" use="Shown per region while the agent streams. Never a whole-page spinner.">
            <div className="max-w-sm space-y-2"><Skeleton className="w-32" /><Skeleton className="h-5 w-full" /><Skeleton className="w-48" /></div>
          </Spec>

          <Spec name="RiskGauge" use="Risk (continuous bar, risk colour) and confidence (segmented, neutral) always render together. Hatched band is the 90% interval. Drag to see the tween.">
            <div className="max-w-md space-y-3">
              <RiskGauge risk={risk} lo={Math.max(0, risk - 0.1)} hi={Math.min(1, risk + 0.06)} confidence={0.3 + risk * 0.6} source="kitchen-sink slider" />
              <input type="range" min={0} max={100} value={risk * 100} onChange={(e) => setRisk(+e.target.value / 100)} aria-label="Demo risk" className="w-full accent-[var(--accent)]" />
            </div>
          </Spec>

          <Spec name="RecCard" use="Compact recommendation: action, approval route, cited policy clause, risk, interval, confidence.">
            <div className="grid max-w-lg grid-cols-2 gap-2">{prior && <RecCard rec={prior} label="Before" muted />}{current && <RecCard rec={current} label="After" />}</div>
          </Spec>

          <Spec name="BeforeAfter" use="The centrepiece. Prior card moves aside, the new one slides in, the diff rows stagger in with changes flashed, and the evidence that caused the change is listed with sources.">
            <div className="max-w-md">
              <Button size="sm" onClick={() => setFlip((n) => n + 1)}>Replay transition</Button>
              <div className="mt-3">{prior && current && <BeforeAfter key={flip} prior={prior} current={current} steps={inv.steps} />}</div>
            </div>
          </Spec>

          <Spec name="Uncertainty" use="Open questions ordered by expected information gain, with the evidence that would resolve each. Resolved ones sink and strike through.">
            <div className="max-w-md">{current && <Uncertainty rec={flip % 2 ? prior! : current} />}</div>
          </Spec>

          <Spec name="ActionBar" use="Allowed actions live; restricted ones disabled with a tooltip naming the policy. Each asks for confirmation, then writes optimistically to the audit trail and rolls back on error.">
            <div className="max-w-md">{current && <ActionBar c={c} rec={current} />}</div>
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
            <Confirm open={open} onOpenChange={setOpen} title="Freeze account on FC-1042?" confirmLabel="Freeze account" onConfirm={() => {}} body="Authorized by ACC-1.4 §3. This is written to the audit trail." />
          </Spec>
        </div>
      </div>
    </div>
  )
}
