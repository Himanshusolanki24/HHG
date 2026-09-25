import { useEffect, useMemo, useRef } from 'react'
import cytoscape, { type Core } from 'cytoscape'
import { useStore } from '../store.ts'
import { band } from '../derive.ts'
import type { CaseView } from '../hooks.ts'
import type { EntityType } from '../api/schemas.ts'
import { Button, Prov, RiskChip, Skeleton, cn } from './ui.tsx'

export const ENTITY: Record<EntityType, { label: string; shape: cytoscape.Css.NodeShape }> = {
  customer: { label: 'Customer', shape: 'round-rectangle' },
  card: { label: 'Card', shape: 'rectangle' },
  device: { label: 'Device profile', shape: 'hexagon' },
  email: { label: 'Email domain', shape: 'tag' },
  region: { label: 'Billing region', shape: 'diamond' },
  transaction: { label: 'Transaction', shape: 'ellipse' },
  prior_case: { label: 'Prior case', shape: 'octagon' },
}

const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()

export function GraphView({ view }: { view: CaseView }) {
  const { inv, path, steps } = view
  const box = useRef<HTMLDivElement>(null)
  const cy = useRef<Core | null>(null)
  const theme = useStore((s) => s.theme)
  const focusNode = useStore((s) => s.focusNode)
  const showNode = useStore((s) => s.showNode)
  const evidenceOnly = useStore((s) => s.evidenceOnly)
  const toggleEvidenceOnly = useStore((s) => s.toggleEvidenceOnly)

  // Build once per investigation.
  useEffect(() => {
    if (!inv || !box.current) return
    // Rings by hop distance from the subject account.
    const hops: Record<string, number> = { [inv.subjectId]: 0 }
    for (let frontier = [inv.subjectId], d = 1; frontier.length; d++) {
      const next: string[] = []
      for (const e of inv.edges) for (const [a, b] of [[e.source, e.target], [e.target, e.source]])
        if (frontier.includes(a) && hops[b] === undefined) { hops[b] = d; next.push(b) }
      frontier = next
    }
    const inst = cytoscape({
      container: box.current,
      elements: [
        ...inv.nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, risk: n.risk, subject: n.id === inv.subjectId ? 1 : 0 } })),
        ...inv.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target, label: `${e.rel} ${e.weight}` } })),
      ],
      layout: { name: 'concentric', concentric: (n) => 10 - (hops[n.id()] ?? 9), levelWidth: () => 1, minNodeSpacing: 48, animate: false, padding: 24 },
      wheelSensitivity: 0.3,
      minZoom: 0.3,
      maxZoom: 1.4,
      boxSelectionEnabled: false,
    })
    inst.on('tap', 'node', (e) => useStore.getState().showNode(e.target.id()))
    inst.on('tap', (e) => { if (e.target === inst) useStore.getState().showNode(null) })
    cy.current = inst
    // Tab panel toggles display:none; refit when it becomes visible again.
    const ro = new ResizeObserver(() => { inst.resize(); if (inst.width() > 0 && !inst.data('fitted')) { inst.fit(undefined, 24); inst.data('fitted', true) } })
    ro.observe(box.current)
    return () => { ro.disconnect(); inst.destroy(); cy.current = null }
  }, [inv])

  // Theme-aware style.
  useEffect(() => {
    const inst = cy.current
    if (!inst) return
    const riskColor = (r: number) => css(`--risk-${{ low: 'low', medium: 'med', high: 'high' }[band(r)]}`)
    inst.style([
      { selector: 'node', style: {
        shape: (n: cytoscape.NodeSingular) => ENTITY[n.data('type') as EntityType].shape,
        'background-color': (n: cytoscape.NodeSingular) => css(`--t-${n.data('type')}`),
        'border-width': 3, 'border-color': (n: cytoscape.NodeSingular) => riskColor(n.data('risk')),
        width: 26, height: 26, label: 'data(label)', color: css('--fg'), 'font-size': 10, 'font-family': 'IBM Plex Sans',
        'text-valign': 'bottom', 'text-margin-y': 4, 'text-background-color': css('--panel'), 'text-background-opacity': 0.85, 'text-background-padding': '1px',
        'transition-property': 'opacity', 'transition-duration': 250,
      } },
      { selector: 'node[subject = 1]', style: { width: 38, height: 38, 'font-weight': 600 } },
      { selector: 'edge', style: {
        width: 1, 'line-color': css('--line-strong'), 'target-arrow-color': css('--line-strong'), 'target-arrow-shape': 'triangle', 'arrow-scale': 0.7,
        'curve-style': 'bezier', label: 'data(label)', 'font-size': 8, color: css('--muted'), 'text-rotation': 'autorotate',
        'text-background-color': css('--panel'), 'text-background-opacity': 1, 'text-background-padding': '1px',
        'transition-property': 'opacity, line-color, width', 'transition-duration': 250,
      } },
      { selector: '.dim', style: { opacity: 0.16 } },
      { selector: '.hidden', style: { display: 'none' } },
      { selector: 'edge.ev', style: { width: 2.5, 'line-color': css('--accent'), 'target-arrow-color': css('--accent'), color: css('--fg') } },
      { selector: 'node.ev', style: { 'underlay-color': css('--accent'), 'underlay-opacity': 0.12, 'underlay-padding': 3 } },
      { selector: 'node.focus', style: { 'overlay-color': css('--accent'), 'overlay-opacity': 0.25, 'overlay-padding': 6 } },
    ])
  }, [inv, theme])

  // Evidence path highlight follows the (replayable) step cursor.
  useEffect(() => {
    const inst = cy.current
    if (!inst) return
    const any = path.nodes.size > 0
    inst.batch(() => {
      inst.elements().removeClass('ev dim hidden')
      if (!any) return
      inst.nodes().forEach((n) => { n.addClass(path.nodes.has(n.id()) || n.data('subject') ? 'ev' : evidenceOnly ? 'hidden' : 'dim') })
      inst.edges().forEach((e) => { e.addClass(path.edges.has(e.id()) ? 'ev' : evidenceOnly ? 'hidden' : 'dim') })
    })
  }, [path, evidenceOnly, inv])

  useEffect(() => {
    const inst = cy.current
    if (!inst) return
    inst.nodes().removeClass('focus')
    if (focusNode) { const n = inst.getElementById(focusNode); n.addClass('focus'); inst.animate({ center: { eles: n } }, { duration: 250 }) }
  }, [focusNode, inv])

  const nodeOrder = useMemo(() => inv?.nodes.map((n) => n.id) ?? [], [inv])
  const onKey = (e: React.KeyboardEvent) => {
    if (!nodeOrder.length) return
    const i = focusNode ? nodeOrder.indexOf(focusNode) : -1
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); showNode(nodeOrder[(i + 1) % nodeOrder.length]) }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); showNode(nodeOrder[(i - 1 + nodeOrder.length) % nodeOrder.length]) }
    if (e.key === 'Escape') showNode(null)
  }

  const node = inv?.nodes.find((n) => n.id === focusNode)
  const cited = node ? steps.filter((s) => s.nodes.includes(node.id)) : []
  const focusLabel = node ? `${ENTITY[node.type].label} ${node.label}, risk ${(node.risk * 100).toFixed(0)}` : 'none'

  if (!inv) return <div className="p-4"><Skeleton className="h-64 w-full" /></div>

  return (
    <div className="relative flex h-full min-h-0">
      <div className="relative min-w-0 flex-1">
        <div
          role="application"
          aria-roledescription="entity relationship graph"
          aria-label={`Entity graph for ${inv.subjectId}. ${inv.nodes.length} entities, ${path.nodes.size} on the evidence path. Arrow keys move between entities, Escape clears. Selected: ${focusLabel}.`}
          tabIndex={0}
          onKeyDown={onKey}
          className="absolute inset-0"
        >
          {/* cytoscape rewrites its container's position, so it gets its own sized child */}
          <div ref={box} className="h-full w-full" />
        </div>
        <div className="pointer-events-none absolute top-2 left-2 flex flex-col gap-2">
          <div className="pointer-events-auto flex items-center gap-2 rounded border border-line bg-panel px-2 py-1">
            <label className="flex items-center gap-1.5 text-xs">
              <input type="checkbox" checked={evidenceOnly} onChange={toggleEvidenceOnly} className="accent-[var(--accent)]" />
              Show evidence path only
            </label>
            <span className="text-2xs text-faint">
              <Prov source="union of nodes/edges touched by visible agent steps">{path.nodes.size} nodes, {path.edges.size} edges</Prov>
            </span>
          </div>
        </div>
        <Legend />
      </div>

      {node && (
        <aside aria-label={`Details for ${node.label}`} className="w-64 shrink-0 overflow-y-auto border-l border-line bg-panel p-3">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="text-2xs text-muted">{ENTITY[node.type].label}</div>
              <div className="text-base font-semibold">{node.label}</div>
            </div>
            <Button size="sm" variant="ghost" onClick={() => showNode(null)} aria-label="Close details">Close</Button>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <RiskChip risk={node.risk} />
            <Prov source={`vertex ${node.id}.risk_score (TigerGraph)`}>{(node.risk * 100).toFixed(0)}</Prov>
          </div>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted">Vertex id</dt><dd className="font-mono text-2xs">{node.id}</dd>
            {Object.entries(node.attrs).map(([k, v]) => (
              <div key={k} className="contents"><dt className="text-muted">{k.replaceAll('_', ' ')}</dt><dd>{v}</dd></div>
            ))}
          </dl>
          <h4 className="mt-4 text-xs font-semibold text-muted">Cited by agent</h4>
          {cited.length === 0 ? <p className="mt-1 text-xs text-faint">Not used as evidence yet.</p> : (
            <ul className="mt-1 space-y-1.5">
              {cited.map((s) => (
                <li key={s.id} className="text-xs"><span className="text-faint">Step {s.seq}</span> {s.title}</li>
              ))}
            </ul>
          )}
        </aside>
      )}
    </div>
  )
}

export function Legend({ className }: { className?: string }) {
  return (
    <div className={cn('absolute bottom-2 left-2 rounded border border-line bg-panel px-2 py-1.5 text-2xs', className)}>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {(Object.keys(ENTITY) as EntityType[]).map((t) => (
          <span key={t} className="flex items-center gap-1">
            <Shape type={t} />{ENTITY[t].label}
          </span>
        ))}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 text-muted">
        <span>Border = risk</span>
        <span className="flex items-center gap-1"><i className="size-2.5 rounded-sm border-2 border-risk-low" />Low</span>
        <span className="flex items-center gap-1"><i className="size-2.5 rounded-sm border-2 border-risk-med" />Medium</span>
        <span className="flex items-center gap-1"><i className="size-2.5 rounded-sm border-2 border-risk-high" />High</span>
        <span className="flex items-center gap-1"><i className="h-0.5 w-4 bg-accent" />Evidence path</span>
      </div>
    </div>
  )
}

function Shape({ type }: { type: EntityType }) {
  const fill = `var(--t-${type})`
  const p: Record<EntityType, React.ReactNode> = {
    customer: <rect x="1" y="2" width="10" height="8" rx="2" fill={fill} />,
    card: <rect x="1" y="2" width="10" height="8" fill={fill} />,
    device: <polygon points="3,1 9,1 12,6 9,11 3,11 0,6" fill={fill} />,
    email: <polygon points="1,2 8,2 11,6 8,10 1,10" fill={fill} />,
    region: <polygon points="6,0 12,6 6,12 0,6" fill={fill} />,
    transaction: <circle cx="6" cy="6" r="5" fill={fill} />,
    prior_case: <polygon points="4,1 8,1 11,4 11,8 8,11 4,11 1,8 1,4" fill={fill} />,
  }
  return <svg width="12" height="12" aria-hidden>{p[type]}</svg>
}
