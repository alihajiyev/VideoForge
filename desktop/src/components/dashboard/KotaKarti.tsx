import type { ReactNode } from 'react'
import { Gauge } from 'lucide-react'
import { useApp } from '@/app/AppContext'
import { Panel, SectionTitle, Spinner } from '@/components/ui/primitives'
import { formatKalan } from '@/lib/utils'
import { useTicker } from '@/lib/hooks'

/**
 * Kota gostergesi (TAHMINI): botun loglarindaki AI cagrilari gunluk sayilir ve
 * Pasifik gece yarisindaki sifirlanmaya kadar gosterilir. Google'in resmi
 * sayaci degildir; botu yavaslatmamak icin yalnizca istatistik amaclidir.
 */
export function KotaKarti(): ReactNode {
  const { quota, refreshQuota } = useApp()
  useTicker(true)

  if (!quota) {
    return (
      <Panel className="p-3.5">
        <SectionTitle title="Gemini kotası" subtitle="Tahmini günlük kullanım" icon={<Gauge className="size-4" />} />
        <div className="flex items-center gap-2 py-4 text-[12px] text-fg-subtle">
          <Spinner /> Sayaç okunuyor...
        </div>
      </Panel>
    )
  }

  const gunlukToplam = quota.limitler.reduce((a, b) => a + b, 0)
  const oran = gunlukToplam > 0 ? Math.min(100, Math.round((quota.aiCagrisi / gunlukToplam) * 100)) : 0
  const kalanMs = quota.sifirlanmaMs - Date.now()

  return (
    <Panel className="p-3.5" flat>
      <SectionTitle
        title="Gemini kotası"
        subtitle="Tahmini günlük kullanım"
        icon={<Gauge className="size-4" />}
        right={
          <button
            onClick={() => void refreshQuota()}
            className="text-[11px] text-fg-subtle transition-colors hover:text-fg"
          >
            Yenile
          </button>
        }
      />

      <div className="mt-3 flex items-end justify-between">
        <div>
          <p className="num text-[20px] font-semibold tracking-[-0.02em] text-fg">{quota.aiCagrisi}</p>
          <p className="text-[11px] text-fg-subtle">bugün sayılan AI çağrısı</p>
        </div>
        <div className="text-right">
          <p className="text-[11px] text-fg-subtle">Sıfırlanma</p>
          <p className="num text-[12.5px] text-fg">{formatKalan(kalanMs)}</p>
        </div>
      </div>

      <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-3)]">
        <div className="h-full rounded-full bg-cyan transition-all duration-500" style={{ width: `${Math.max(2, oran)}%` }} />
      </div>

      <div className="mt-2.5 space-y-1 border-t border-border pt-2.5">
        {quota.modeller.map((m, i) => (
          <div key={m} className="flex items-center justify-between gap-3 font-mono text-[11px]">
            <span className="truncate text-fg-muted">{m}</span>
            <span className="num shrink-0 text-fg-subtle">RPD {quota.limitler[i] ?? '—'}</span>
          </div>
        ))}
      </div>

      <p className="mt-2 text-[10.5px] leading-relaxed text-fg-subtle">
        Tahmini değer: bot loglarındaki AI adımları sayılır. Resmî Google sayacı değildir.
      </p>
    </Panel>
  )
}
