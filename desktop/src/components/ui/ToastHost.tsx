import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { useApp } from '@/app/AppContext'
import { cn } from '@/lib/utils'

const TONE = {
  info: { cls: 'text-cyan', icon: <Info className="size-4" /> },
  success: { cls: 'text-success', icon: <CheckCircle2 className="size-4" /> },
  warn: { cls: 'text-warn', icon: <AlertTriangle className="size-4" /> },
  error: { cls: 'text-danger', icon: <XCircle className="size-4" /> },
} as const

export function ToastHost(): ReactNode {
  const { toasts, dismissToast } = useApp()
  if (!toasts.length) return null

  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-[100] flex w-[330px] flex-col gap-2">
      {toasts.map((toast) => {
        const tone = TONE[toast.tone]
        return (
          <div
            key={toast.id}
            className={cn(
              'panel pointer-events-auto flex items-start gap-2.5 px-3 py-2.5 shadow-[var(--shadow-pop)]',
              'animate-[rise_0.24s_cubic-bezier(0.22,1,0.36,1)]',
            )}
          >
            <span className={cn('mt-0.5 shrink-0', tone.cls)}>{tone.icon}</span>
            <div className="min-w-0 flex-1">
              <p className="text-[12.5px] font-medium text-fg">{toast.title}</p>
              {toast.message ? <p className="mt-0.5 text-[11.5px] break-words text-fg-subtle">{toast.message}</p> : null}
            </div>
            <button onClick={() => dismissToast(toast.id)} className="text-fg-subtle transition-colors hover:text-fg">
              <X className="size-3.5" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
