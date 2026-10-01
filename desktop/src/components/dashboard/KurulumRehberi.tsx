import type { ReactNode } from 'react'
import { CheckCircle2, CircleAlert, Rocket, X } from 'lucide-react'
import { useApp } from '@/app/AppContext'
import { Badge, Button, Panel, SectionTitle } from '@/components/ui/primitives'
import { cn } from '@/lib/utils'
import type { PageKey } from '@/components/layout/Sidebar'

/**
 * Ilk kurulum rehberi: ortam kontrollerinden (Python, bot dosyalari, modal,
 * google-genai, ffmpeg, cookies) otomatik bir kontrol listesi uretir. Hepsi
 * tamamsa ya da kullanici kapattiysa gosterilmez.
 */
export function KurulumRehberi({ onNavigate }: { onNavigate: (page: PageKey) => void }): ReactNode {
  const { env, envLoading, settings, saveSettings, refreshEnv } = useApp()

  if (settings?.onboardingDone) return null
  if (env.length === 0) return null

  const eksik = env.filter((e) => !e.ok)
  if (eksik.length === 0) return null

  const kapat = (): void => void saveSettings({ onboardingDone: true })

  return (
    <Panel className="p-3.5" flat>
      <SectionTitle
        title="Kurulumu tamamlayın"
        subtitle={`${env.length - eksik.length}/${env.length} kontrol hazır`}
        icon={<Rocket className="size-4" />}
        right={
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" onClick={() => void refreshEnv()} disabled={envLoading}>
              Yeniden kontrol
            </Button>
            <button
              onClick={kapat}
              title="Rehberi kapat"
              className="grid size-7 place-items-center rounded-[7px] text-fg-subtle transition-colors hover:bg-[var(--surface-2)] hover:text-fg"
            >
              <X className="size-3.5" />
            </button>
          </div>
        }
      />

      <ul className="mt-3 space-y-1.5">
        {env.map((item) => (
          <li key={item.id} className="flex items-start gap-2 text-[12px]">
            <span className={cn('mt-0.5 shrink-0', item.ok ? 'text-success' : 'text-warn')}>
              {item.ok ? <CheckCircle2 className="size-3.5" /> : <CircleAlert className="size-3.5" />}
            </span>
            <div className="min-w-0">
              <span className="text-fg">{item.label}</span>
              <span className="ml-2 text-[11px] text-fg-subtle">{item.detail}</span>
              {!item.ok && item.fix ? <p className="mt-0.5 text-[11px] text-warn">{item.fix}</p> : null}
            </div>
          </li>
        ))}
      </ul>

      <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
        <Button size="sm" icon={<Rocket className="size-3.5" />} onClick={() => onNavigate('settings')}>
          Ayarlara git
        </Button>
        <Badge tone="warn">{eksik.length} eksik</Badge>
      </div>
    </Panel>
  )
}
