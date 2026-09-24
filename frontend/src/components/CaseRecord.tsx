import { useState } from 'react'
import type { CaseView } from '../hooks.ts'
import { useStore } from '../store.ts'
import { caseRecord } from '../derive.ts'
import { Button, Skeleton, cn } from './ui.tsx'

export function CaseRecord({ view }: { view: CaseView }) {
  const audit = useStore((s) => s.audit)
  const [raw, setRaw] = useState(false)
  const [copied, setCopied] = useState<'idle' | 'ok' | 'fail'>('idle')
  if (!view.c || !view.inv) return <div className="p-4"><Skeleton className="h-64 w-full" /></div>
  const rec = caseRecord(view.c, view.inv, view.steps, audit)
  const json = JSON.stringify(rec, null, 2)
  const copy = async () => {
    try { await navigator.clipboard.writeText(json); setCopied('ok') } catch { setCopied('fail') }
    setTimeout(() => setCopied('idle'), 1600)
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
        <span className="text-xs text-muted">Vertex <span className="font-mono text-fg">{rec.vertex}</span> with {rec.edges.length} edges, as upserted to TigerGraph</span>
        <div className="ml-auto flex gap-1" role="radiogroup" aria-label="Record view">
          {([[false, 'Structured'], [true, 'Raw JSON']] as const).map(([v, l]) => (
            <button key={l} role="radio" aria-checked={raw === v} onClick={() => setRaw(v)}
              className={cn('h-6 rounded-sm border px-2 text-xs', raw === v ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted hover:text-fg')}>{l}</button>
          ))}
          <Button size="sm" onClick={copy} aria-live="polite">{copied === 'ok' ? 'Copied' : copied === 'fail' ? 'Copy blocked by browser' : 'Copy JSON'}</Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {raw ? (
          <pre className="font-mono text-xs leading-5 text-fg">{json}</pre>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <table className="w-full text-xs">
              <caption className="pb-1 text-left text-xs font-semibold text-muted">Attributes</caption>
              <tbody>
                <tr className="border-b border-line"><th className="py-1 pr-3 text-left font-normal text-muted">primary_id</th><td className="font-mono">{rec.primary_id}</td></tr>
                {Object.entries(rec.attributes).map(([k, v]) => (
                  <tr key={k} className="border-b border-line">
                    <th className="py-1 pr-3 text-left font-normal text-muted">{k}</th>
                    <td className="font-mono">{v === null ? <span className="text-faint">null</span> : Array.isArray(v) ? `[${v.join(', ')}]` : String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table className="w-full text-xs">
              <caption className="pb-1 text-left text-xs font-semibold text-muted">Edges</caption>
              <tbody>
                {rec.edges.map((e, i) => (
                  <tr key={i} className="border-b border-line">
                    <th className="py-1 pr-3 text-left font-mono font-normal text-muted">{e.type}</th>
                    <td className="font-mono">{e.to}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
