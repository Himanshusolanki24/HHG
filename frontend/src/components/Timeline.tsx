import { useMemo, useState } from 'react'
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import type { CaseView } from '../hooks.ts'
import { useStore } from '../store.ts'
import type { AgentStep } from '../api/schemas.ts'
import { Skeleton, cn } from './ui.tsx'

const fmtTime = (t: number) => new Date(t).toISOString().slice(5, 16).replace('T', ' ')
const fmtAmt = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
const LANE: Record<AgentStep['tool'], number> = {
  gsql: 3, graphrag: 3, policy_lookup: 3, recommend: 2, evidence_request: 1, evidence_response: 1,
}
const LANE_NAME: Record<number, string> = { 3: 'Agent tools', 2: 'Recommendation', 1: 'Evidence' }
const MARGIN = { top: 8, right: 16, bottom: 0, left: 8 }
const Y_WIDTH = 96

type Pt = { x: number; y: number; name: string; detail: string; source: string; stepId?: string }

export function Timeline({ view }: { view: CaseView }) {
  const { inv, steps } = view
  const showStep = useStore((s) => s.showStep)
  const [win, setWin] = useState<'all' | 'run'>('all')

  const data = useMemo(() => {
    if (!inv) return null
    const pt = (s: AgentStep): Pt => ({ x: Date.parse(s.at), y: LANE[s.tool], name: s.title, detail: s.summary, source: `agent step ${s.seq} (${s.tool})`, stepId: s.id })
    const tx = (flagged: boolean) => inv.transactions.filter((t) => t.flagged === flagged).map((t): Pt => ({
      x: Date.parse(t.at), y: t.amount, name: `${t.direction === 'in' ? 'In from' : 'Out to'} ${t.merchant}`, detail: fmtAmt(t.amount), source: `transaction ${t.id}`,
    }))
    const alert = Date.parse(inv.alertAt)
    const times = [...inv.transactions.map((t) => Date.parse(t.at)), ...steps.map((s) => Date.parse(s.at)), alert]
    const end = Math.max(...times)
    return {
      alert,
      domain: win === 'all'
        ? [Math.min(...times) - 10 * 60e3, end + 5 * 60e3]
        : [alert - 3 * 60e3, Math.max(end, alert + 5 * 60e3) + 2 * 60e3],
      normal: tx(false), flagged: tx(true),
      tools: steps.filter((s) => LANE[s.tool] === 3).map(pt),
      recs: steps.filter((s) => s.tool === 'recommend').map(pt),
      req: steps.filter((s) => s.tool === 'evidence_request').map(pt),
      res: steps.filter((s) => s.tool === 'evidence_response').map(pt),
    }
  }, [inv, steps, win])

  if (!data) return <div className="p-4"><Skeleton className="h-64 w-full" /></div>

  const inDomain = (p: Pt) => p.x >= data.domain[0] && p.x <= data.domain[1]
  const onPick = (p: unknown) => { const id = (p as { payload?: Pt }).payload?.stepId; if (id) showStep(id) }
  // Explicit, evenly spaced ticks: auto "nice" ticks collide (duplicate keys) when the window is only minutes wide.
  const ticks = Array.from({ length: 7 }, (_, i) => Math.round(data.domain[0] + ((data.domain[1] - data.domain[0]) * i) / 6))
  const xAxis = (hide: boolean) => (
    <XAxis type="number" dataKey="x" domain={data.domain} scale="time" tickFormatter={fmtTime} hide={hide} allowDataOverflow
      stroke="var(--line-strong)" tick={{ fill: 'var(--muted)', fontSize: 11 }} ticks={ticks} />
  )
  const alertLine = <ReferenceLine x={data.alert} stroke="var(--risk-high)" strokeDasharray="3 3" label={{ value: 'Alert', position: 'insideTopRight', fill: 'var(--risk-high)', fontSize: 11 }} />

  return (
    <div className="flex h-full min-h-0 flex-col p-3">
      <div className="flex items-center justify-between gap-2 pb-2">
        <div role="radiogroup" aria-label="Time window" className="flex gap-1">
          {([['all', 'Full history'], ['run', 'Agent run']] as const).map(([k, l]) => (
            <button key={k} role="radio" aria-checked={win === k} onClick={() => setWin(k)}
              className={cn('h-6 rounded-sm border px-2 text-xs', win === k ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted hover:text-fg')}>{l}</button>
          ))}
        </div>
        <ul className="flex flex-wrap gap-x-3 text-2xs text-muted" aria-label="Marker legend">
          <li className="flex items-center gap-1"><Dot fill="var(--muted)" />Transaction</li>
          <li className="flex items-center gap-1"><Dot fill="var(--risk-high)" />Flagged transaction</li>
          <li className="flex items-center gap-1"><Sq />Agent tool call</li>
          <li className="flex items-center gap-1"><Star />Recommendation</li>
          <li className="flex items-center gap-1"><Tri />Evidence requested</li>
          <li className="flex items-center gap-1"><Dia />Evidence received</li>
        </ul>
      </div>

      <figure className="min-h-0 flex-1" aria-label="Transactions by amount over time, log scale">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={MARGIN}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" />
            {xAxis(true)}
            <YAxis type="number" dataKey="y" scale="log" domain={[0.5, (max: number) => max * 2]} width={Y_WIDTH} allowDataOverflow
              tickFormatter={(v) => fmtAmt(v)} stroke="var(--line-strong)" tick={{ fill: 'var(--muted)', fontSize: 11 }}
              label={{ value: 'Amount (log)', angle: -90, position: 'insideLeft', fill: 'var(--faint)', fontSize: 11 }} />
            <ZAxis range={[36, 36]} />
            {alertLine}
            <Tooltip content={<Tip />} cursor={false} isAnimationActive={false} />
            <Scatter data={data.normal.filter(inDomain)} fill="var(--muted)" isAnimationActive={false} />
            <Scatter data={data.flagged.filter(inDomain)} fill="var(--risk-high)" isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </figure>

      <figure className="h-[112px] shrink-0 border-t border-line" aria-label="Agent actions and evidence events on the same time axis">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ ...MARGIN, top: 6 }}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" horizontal={false} />
            {xAxis(false)}
            <YAxis type="number" dataKey="y" domain={[0.5, 3.5]} ticks={[1, 2, 3]} width={Y_WIDTH} tickFormatter={(v) => LANE_NAME[v]}
              stroke="var(--line-strong)" tick={{ fill: 'var(--muted)', fontSize: 11 }} />
            <ZAxis range={[64, 64]} />
            {alertLine}
            <Tooltip content={<Tip />} cursor={false} isAnimationActive={false} />
            <Scatter data={data.tools.filter(inDomain)} shape="square" fill="var(--accent)" onClick={onPick} className="cursor-pointer" isAnimationActive={false} />
            <Scatter data={data.recs.filter(inDomain)} shape="star" fill="var(--fg)" onClick={onPick} className="cursor-pointer" isAnimationActive={false} />
            <Scatter data={data.req.filter(inDomain)} shape="triangle" fill="none" stroke="var(--conf)" strokeWidth={1.5} onClick={onPick} className="cursor-pointer" isAnimationActive={false} />
            <Scatter data={data.res.filter(inDomain)} shape="diamond" fill="var(--conf)" onClick={onPick} className="cursor-pointer" isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
      </figure>
      {win === 'all' && steps.length > 0 && <p className="pt-1 text-2xs text-faint">Agent activity is compressed at this scale. Switch to Agent run to spread it out. Click a marker to open its trace step.</p>}
    </div>
  )
}

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Pt }[] }) {
  const p = active && payload?.[0]?.payload
  if (!p) return null
  return (
    <div className="max-w-64 rounded border border-line-strong bg-raised px-2.5 py-2 text-xs shadow-lg shadow-black/30">
      <div className="text-2xs text-muted">{fmtTime(p.x)} UTC</div>
      <div className="font-medium">{p.name}</div>
      <div className="text-muted">{p.detail}</div>
      <div className="mt-1 font-mono text-2xs text-faint">{p.source}</div>
    </div>
  )
}

const Dot = ({ fill }: { fill: string }) => <svg width="10" height="10" aria-hidden><circle cx="5" cy="5" r="4" fill={fill} /></svg>
const Sq = () => <svg width="10" height="10" aria-hidden><rect x="1" y="1" width="8" height="8" fill="var(--accent)" /></svg>
const Star = () => <svg width="10" height="10" aria-hidden><polygon points="5,0 6.2,3.6 10,3.8 7,6.1 8.1,10 5,7.7 1.9,10 3,6.1 0,3.8 3.8,3.6" fill="var(--fg)" /></svg>
const Tri = () => <svg width="10" height="10" aria-hidden><polygon points="5,1 9,9 1,9" fill="none" stroke="var(--conf)" strokeWidth="1.3" /></svg>
const Dia = () => <svg width="10" height="10" aria-hidden><polygon points="5,0 10,5 5,10 0,5" fill="var(--conf)" /></svg>
