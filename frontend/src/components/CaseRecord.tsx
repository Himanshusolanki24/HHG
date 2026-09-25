import { useState } from 'react'
import type { CaseView } from '../hooks.ts'
import type { Action } from '../api/schemas.ts'
import { PATTERN_LABEL } from '../derive.ts'
import { Button, Skeleton, Tag, cn } from './ui.tsx'

const money = (n: number) => `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return <tr className="border-b border-line align-top"><th className="w-44 py-1 pr-3 text-left font-normal text-muted">{k}</th><td className="py-1">{children}</td></tr>
}

function Actions({ list }: { list: Action[] }) {
  return <ol className="space-y-0.5">{list.map((a) => <li key={a.action}><span className="font-medium">{a.action}</span> <Tag>{a.route}</Tag> <span className="text-muted">{a.reason}</span></li>)}</ol>
}

/** The answer file exactly as submitted (dataset README "Answer Format") and as written to the graph. */
export function CaseRecord({ view }: { view: CaseView }) {
  const [raw, setRaw] = useState(false)
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle')
  if (!view.inv) return <div className="p-4"><Skeleton className="h-64 w-full" /></div>
  const a = view.inv.answer
  const c = a.case
  const json = JSON.stringify(a, null, 2)
  const copy = async () => {
    try { await navigator.clipboard.writeText(json); setCopied('ok') } catch { setCopied('fail') }
    setTimeout(() => setCopied('idle'), 1600)
  }
  const download = URL.createObjectURL(new Blob([json], { type: 'application/json' }))

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
        <span className="text-xs text-muted">
          Answer file <span className="font-mono text-fg">cases/{a.case_id}.json</span>
          {c.written_to_graph ? <>, written to TigerGraph as <span className="font-mono text-fg">{c.graph_case_id}</span></> : ', kept in local case memory (TigerGraph not connected)'}
        </span>
        <div className="ml-auto flex gap-1" role="radiogroup" aria-label="Record view">
          {([[false, 'Structured'], [true, 'Raw JSON']] as const).map(([v, l]) => (
            <button key={l} role="radio" aria-checked={raw === v} onClick={() => setRaw(v)}
              className={cn('h-6 rounded-sm border px-2 text-xs', raw === v ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted hover:text-fg')}>{l}</button>
          ))}
          <Button size="sm" onClick={copy} aria-live="polite">{copied === 'ok' ? 'Copied' : copied === 'fail' ? 'Copy blocked by browser' : 'Copy JSON'}</Button>
          <a href={download} download={`${a.case_id}.json`} className="inline-flex h-6 items-center rounded border border-line-strong px-2 text-xs hover:border-accent hover:text-accent">Download</a>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {raw ? <pre className="font-mono text-xs leading-5 text-fg">{json}</pre> : (
          <div className="grid gap-5 xl:grid-cols-2">
            <table className="w-full text-xs">
              <caption className="pb-1 text-left text-xs font-semibold text-muted">Case</caption>
              <tbody>
                <Row k="Status">{c.status.replace('_', ' ')}</Row>
                <Row k="Verdict">{c.verdict}, probability {c.fraud_probability.toFixed(2)}</Row>
                <Row k="Pattern">{PATTERN_LABEL[c.pattern]}{c.pattern_description && <p className="mt-0.5 text-muted">{c.pattern_description}</p>}</Row>
                <Row k="Exposure">{money(c.exposure_usd)}</Row>
                <Row k="Affected transactions">{c.affected_txn_ids.join(', ') || 'none'}{c.first_suspicious_txn_id && <span className="text-muted"> (first {c.first_suspicious_txn_id})</span>}</Row>
                <Row k="Connected cards">{c.connected_card_ids.length ? `${c.connected_card_ids.length}: ${c.connected_card_ids.join(', ')}` : 'none'}</Row>
                <Row k="Device profiles">{c.connected_device_profiles.join('; ') || 'none'}</Row>
                <Row k="Similar prior cases">{c.similar_prior_cases.join(', ') || 'none'}</Row>
                <Row k="Summary">{c.summary}</Row>
                <Row k="Stop reason">{a.stop_reason}</Row>
                <Row k="Cost">{a.tool_calls} tool calls, {a.tokens.toLocaleString()} tokens, {a.latency_s}s</Row>
              </tbody>
            </table>
            <table className="w-full text-xs">
              <caption className="pb-1 text-left text-xs font-semibold text-muted">Evidence and decisions</caption>
              <tbody>
                <Row k="Evidence">
                  <ol className="space-y-1">{c.evidence.map((e, i) => <li key={i}>{e.claim} <span className="font-mono text-2xs text-faint">[{e.source}: {e.ref}]</span></li>)}</ol>
                </Row>
                <Row k="Evidence requests">{a.evidence_requests.length ? a.evidence_requests.map((r) => <div key={r.type}><span className="font-medium">{r.type}</span> after step {r.asked_after_step}: <span className="text-muted">{r.assumed_response}</span></div>) : 'none'}</Row>
                <Row k="Actions before evidence"><Actions list={a.next_best_actions.initial} /></Row>
                <Row k="Actions after evidence"><Actions list={a.next_best_actions.final} /></Row>
                <Row k="What changed">{a.next_best_actions.what_changed}</Row>
                <Row k="Report (SAR)">{a.sar.file ? <>File: {a.sar.reason}<p className="mt-1">{a.sar.narrative}</p></> : `Not filed. ${a.sar.reason}`}</Row>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
