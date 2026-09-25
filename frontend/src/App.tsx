import { useEffect, useState } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import { useCaseView } from './hooks.ts'
import { useStore, type Tab } from './store.ts'
import { isMock } from './api/client.ts'
import { mockControl } from './api/mock.ts'
import { CaseQueue, PATTERN, TRIGGER } from './components/CaseQueue.tsx'
import { GraphView } from './components/GraphView.tsx'
import { Timeline } from './components/Timeline.tsx'
import { AgentTrace } from './components/AgentTrace.tsx'
import { CaseRecord } from './components/CaseRecord.tsx'
import { DecisionPanel } from './components/DecisionPanel.tsx'
import { ReplayBar } from './components/ReplayBar.tsx'
import { Button, Skeleton, cn } from './components/ui.tsx'

const TABS: [Tab, string][] = [['graph', 'Graph'], ['timeline', 'Timeline'], ['trace', 'Agent trace'], ['record', 'Case record']]

export function TopBar() {
  const theme = useStore((s) => s.theme)
  const toggleTheme = useStore((s) => s.toggleTheme)
  const [failNext, setFailNext] = useState(false)
  return (
    <header className="flex h-9 shrink-0 items-center gap-3 border-b border-line bg-panel px-3">
      <span className="text-sm font-semibold">Case Desk</span>
      <span className="text-xs text-muted">Fraud investigations, TigerGraph agent</span>
      {isMock && <span className="rounded-sm border border-line px-1.5 text-2xs text-muted">Fixture data</span>}
      <div className="ml-auto flex items-center gap-3">
        {isMock && (
          <label className="flex items-center gap-1.5 text-xs text-muted" title="Makes the next analyst action fail so you can see the optimistic rollback">
            <input type="checkbox" checked={failNext} onChange={(e) => { mockControl.failNext = e.target.checked; setFailNext(e.target.checked) }} className="accent-[var(--accent)]" />
            Fail next action
          </label>
        )}
        <a href="/kitchen-sink" className="text-xs text-accent hover:underline">Components</a>
        <Button size="sm" variant="ghost" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>{theme === 'dark' ? 'Light theme' : 'Dark theme'}</Button>
      </div>
    </header>
  )
}

export default function App() {
  const view = useCaseView()
  const tab = useStore((s) => s.tab)
  const setTab = useStore((s) => s.setTab)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (e.metaKey || e.ctrlKey || e.altKey || /INPUT|SELECT|TEXTAREA/.test(t.tagName)) return
      const i = ['1', '2', '3', '4'].indexOf(e.key)
      if (i >= 0) setTab(TABS[i][0])
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setTab])

  const { c } = view
  return (
    <div className="flex h-full flex-col">
      <TopBar />
      <main className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)_400px] max-lg:grid-cols-[240px_minmax(0,1fr)_340px]">
        <CaseQueue />
        <section aria-label="Investigation canvas" className="flex min-h-0 min-w-0 flex-col">
          {!c ? (
            <div className="m-auto max-w-sm p-6 text-sm text-muted">
              <p className="text-base text-fg">Open a case to start.</p>
              <p className="mt-1">Press Enter to open the highlighted case, or click any row. HHG-014 is a device shared across 28 cards; HHG-006 splits purchases just under $500.</p>
            </div>
          ) : (
            <Tabs.Root value={tab} onValueChange={(v) => setTab(v as Tab)} className="flex min-h-0 flex-1 flex-col">
              <div className="flex items-end gap-4 border-b border-line px-3 pt-2">
                <div className="min-w-0 pb-2">
                  <div className="flex items-baseline gap-2">
                    <h1 className="text-base font-semibold">{c.id}</h1>
                    <span className="truncate text-sm">{c.title}</span>
                  </div>
                  <div className="text-xs text-muted">{TRIGGER[c.trigger]} trigger, {PATTERN[c.pattern].toLowerCase()}{view.inv && `, subject ${view.inv.subjectId}, alert ${view.inv.alertAt.slice(11, 16)} UTC`}</div>
                </div>
                <Tabs.List aria-label="Investigation views" className="ml-auto flex shrink-0">
                  {TABS.map(([k, l], i) => (
                    <Tabs.Trigger key={k} value={k} className={cn('-mb-px border-b-2 px-3 py-2 text-sm', tab === k ? 'border-accent text-fg' : 'border-transparent text-muted hover:text-fg')}>
                      {l} <span className="text-2xs text-faint">{i + 1}</span>
                    </Tabs.Trigger>
                  ))}
                </Tabs.List>
              </div>
              {c.hasRun ? (
                <>
                  <ReplayBar view={view} />
                  {TABS.map(([k]) => (
                    <Tabs.Content key={k} value={k} className="min-h-0 flex-1 data-[state=inactive]:hidden" forceMount={k === 'graph' ? true : undefined}>
                      {k === 'graph' && <GraphView view={view} />}
                      {k === 'timeline' && <Timeline view={view} />}
                      {k === 'trace' && <AgentTrace view={view} />}
                      {k === 'record' && <CaseRecord view={view} />}
                    </Tabs.Content>
                  ))}
                </>
              ) : (
                <div className="p-6 text-sm text-muted">
                  <Skeleton className="mb-4 h-40 w-full opacity-40" />
                  <p className="text-fg">No agent run for {c.id} yet.</p>
                  <p className="mt-1">Run <code>python agent.py {c.id}</code> in backend/, then <code>npm run sync</code>, or connect the live API with VITE_API_URL.</p>
                </div>
              )}
            </Tabs.Root>
          )}
        </section>
        <DecisionPanel view={view} />
      </main>
    </div>
  )
}
