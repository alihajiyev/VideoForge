import type { ReactNode } from 'react'
import { Check, Loader2 } from 'lucide-react'
import type { JobStatus, StageDef } from '@shared/types'
import { cn } from '@/lib/utils'

export function StageTimeline({
  stages,
  index,
  status,
}: {
  stages: StageDef[]
  index: number
  status: JobStatus
}): ReactNode {
  if (!stages.length) return null
  return (
    <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
      {stages.map((stage, i) => {
        const done = i < index || (status !== 'running' && status === 'done' && i <= index)
        const active = i === index && status === 'running'
        return (
          <div key={stage.key} className="flex items-center gap-1">
            <div
              className={cn(
                'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11.5px] transition-colors',
                active
                  ? 'border-[color-mix(in_oklab,var(--brand)_45%,transparent)] bg-brand-soft text-brand-text'
                  : done
                    ? 'border-[color-mix(in_oklab,var(--success)_30%,transparent)] bg-success-soft text-success'
                    : 'border-border bg-[var(--surface-2)] text-fg-subtle',
              )}
            >
              {active ? (
                <Loader2 className="size-3 animate-spin" />
              ) : done ? (
                <Check className="size-3" />
              ) : (
                <span className="num text-[10px]">{i + 1}</span>
              )}
              <span className="font-medium">{stage.label}</span>
            </div>
            {i < stages.length - 1 ? (
              <span
                className={cn(
                  'h-px w-4',
                  i < index ? 'bg-[color-mix(in_oklab,var(--success)_45%,transparent)]' : 'bg-border',
                )}
              />
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
