import { useEffect } from 'react'
import { useStore } from '../store.ts'
import type { CaseView } from '../hooks.ts'
import { TOOL } from './AgentTrace.tsx'
import { Button } from './ui.tsx'

const STEP_MS = 900

/** Re-plays the agent run by moving the step cursor; every pane derives from it. */
export function ReplayBar({ view }: { view: CaseView }) {
  const { allSteps, streaming } = view
  const cursor = useStore((s) => s.cursor)
  const playing = useStore((s) => s.playing)
  const { setCursor, setPlaying } = useStore.getState()
  const n = allSteps.length
  const pos = cursor ?? n

  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      const c = useStore.getState().cursor ?? 0
      if (c >= n) { setPlaying(false); setCursor(null) } else setCursor(c + 1)
    }, STEP_MS)
    return () => clearInterval(t)
  }, [playing, n, setCursor, setPlaying])

  const shown = pos > 0 ? allSteps[pos - 1] : undefined
  return (
    <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
      {playing ? (
        <Button size="sm" onClick={() => setPlaying(false)}>Pause</Button>
      ) : (
        <Button size="sm" disabled={streaming || n === 0} onClick={() => { if (cursor === null || cursor >= n) setCursor(0); setPlaying(true) }}>
          {cursor !== null && cursor < n ? 'Resume replay' : 'Replay investigation'}
        </Button>
      )}
      <input
        type="range"
        min={0}
        max={n}
        value={pos}
        disabled={n === 0}
        onChange={(e) => { setPlaying(false); const v = +e.target.value; setCursor(v >= n && !streaming ? null : v) }}
        aria-label="Replay position"
        aria-valuetext={shown ? `Step ${pos} of ${n}: ${shown.title}` : `Before step 1 of ${n}`}
        className="h-1 min-w-24 flex-1 accent-[var(--accent)]"
      />
      <span className="w-[260px] truncate text-xs text-muted" aria-live="polite">
        {n === 0 ? 'Waiting for first agent step' : shown ? <><span className="text-fg">{pos}/{n}</span> {TOOL[shown.tool]}: {shown.title}</> : `0/${n} Alert raised`}
      </span>
      <Button size="sm" variant={cursor === null ? 'ghost' : 'outline'} disabled={cursor === null} onClick={() => { setPlaying(false); setCursor(null) }}>
        {cursor === null ? (streaming ? 'Live' : 'Latest') : 'Jump to latest'}
      </Button>
    </div>
  )
}
