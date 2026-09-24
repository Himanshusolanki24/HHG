// shadcn/ui-style primitives (Radix + Tailwind), trimmed to what the console uses.
import * as React from 'react'
import * as TooltipP from '@radix-ui/react-tooltip'
import * as AlertP from '@radix-ui/react-alert-dialog'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { band, type Band } from '../derive.ts'

export const cn = (...c: ClassValue[]) => twMerge(clsx(c))

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'outline' | 'ghost'; size?: 'sm' | 'md' }
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant = 'outline', size = 'md', ...p }, ref) => (
  <button
    ref={ref}
    className={cn(
      'inline-flex items-center justify-center gap-1 rounded border whitespace-nowrap font-medium select-none',
      'disabled:cursor-not-allowed disabled:opacity-45',
      size === 'sm' ? 'h-6 px-2 text-xs' : 'h-7 px-3 text-sm',
      variant === 'primary' && 'border-accent bg-accent text-accent-ink hover:brightness-110',
      variant === 'outline' && 'border-line-strong bg-panel text-fg hover:border-accent hover:text-accent',
      variant === 'ghost' && 'border-transparent text-muted hover:text-fg',
      className,
    )}
    {...p}
  />
))

export const riskText: Record<Band, string> = { low: 'text-risk-low', medium: 'text-risk-med', high: 'text-risk-high' }
export const riskBg: Record<Band, string> = { low: 'bg-risk-low', medium: 'bg-risk-med', high: 'bg-risk-high' }

/** Risk band chip: the only place green/amber/red appear as fills. */
export function RiskChip({ risk, className }: { risk: number; className?: string }) {
  const b = band(risk)
  return (
    <span className={cn('inline-flex items-center gap-1 text-xs font-medium', riskText[b], className)}>
      <span className={cn('size-2 rounded-full', riskBg[b])} aria-hidden />
      {b[0].toUpperCase() + b.slice(1)}
    </span>
  )
}

export function Tag({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn('inline-flex h-5 items-center rounded-sm border border-line px-1.5 text-2xs text-muted', className)}>{children}</span>
}

export function Tip({ content, children, side = 'top' }: { content: React.ReactNode; children: React.ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  return (
    <TooltipP.Root>
      <TooltipP.Trigger asChild>{children}</TooltipP.Trigger>
      <TooltipP.Portal>
        <TooltipP.Content
          side={side}
          sideOffset={4}
          collisionPadding={8}
          className="z-50 max-w-72 rounded border border-line-strong bg-raised px-2.5 py-2 text-xs text-fg shadow-lg shadow-black/30"
        >
          {content}
        </TooltipP.Content>
      </TooltipP.Portal>
    </TooltipP.Root>
  )
}

/** Provenance: any number or claim wrapped in this reveals where it came from on hover or focus. */
export function Prov({ source, detail, children, className }: { source: string; detail?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <Tip content={<><div className="text-2xs text-muted">Source</div><div className="font-mono text-2xs">{source}</div>{detail && <div className="mt-1.5 text-xs">{detail}</div>}</>}>
      <span tabIndex={0} className={cn('cursor-help underline decoration-faint decoration-dotted underline-offset-[3px]', className)}>{children}</span>
    </Tip>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton h-3', className)} aria-hidden />
}

export function SectionHead({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2 pb-1.5">
      <h3 className="text-xs font-semibold text-muted">{children}</h3>
      {aside}
    </div>
  )
}

export function Confirm({ open, onOpenChange, title, body, confirmLabel, onConfirm }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; body: React.ReactNode; confirmLabel: string; onConfirm: () => void
}) {
  return (
    <AlertP.Root open={open} onOpenChange={onOpenChange}>
      <AlertP.Portal>
        <AlertP.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <AlertP.Content className="fixed top-1/2 left-1/2 z-50 w-[min(440px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 rounded border border-line-strong bg-raised p-4 shadow-2xl shadow-black/40">
          <AlertP.Title className="text-base font-semibold">{title}</AlertP.Title>
          <AlertP.Description asChild><div className="mt-2 text-sm text-muted">{body}</div></AlertP.Description>
          <div className="mt-4 flex justify-end gap-2">
            <AlertP.Cancel asChild><Button>Cancel</Button></AlertP.Cancel>
            <AlertP.Action asChild><Button variant="primary" onClick={onConfirm}>{confirmLabel}</Button></AlertP.Action>
          </div>
        </AlertP.Content>
      </AlertP.Portal>
    </AlertP.Root>
  )
}
