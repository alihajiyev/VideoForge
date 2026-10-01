import type { ReactNode } from 'react'
import { Coins } from 'lucide-react'
import { useApp } from '@/app/AppContext'
import { Panel, SectionTitle, Spinner } from '@/components/ui/primitives'
import { formatRelative, formatUsd, KIND_LABEL, cn } from '@/lib/utils'

/**
 * Harcama karti: botun bildirdigi Modal GPU maliyetleri kalici defterden
 * okunur (bkz. electron/data/spend.ts). Bot koduna dokunmaz.
 */
export function MaliyetKarti(): ReactNode {
  const { spend, refreshSpend } = useApp()

  if (!spend) {
    return (
      <Panel className="p-3.5">
        <SectionTitle title="Maliyet" subtitle="Modal GPU harcaması" icon={<Coins className="size-4" />} />
        <div className="flex items-center gap-2 py-4 text-[12px] text-fg-subtle">
          <Spinner /> Defter okunuyor...
        </div>
      </Panel>
    )
  }

  const son30 = spend.gunler.slice(-14)
  const maks = Math.max(0.0001, ...son30.map((g) => g.usd))
  const turler = Object.entries(spend.ortalama)

  return (
    <Panel className="p-3.5" flat>
      <SectionTitle
        title="Maliyet"
        subtitle="Modal GPU harcaması (kalıcı defter)"
        icon={<Coins className="size-4" />}
        right={
          <button
            onClick={() => void refreshSpend()}
            className="text-[11px] text-fg-subtle transition-colors hover:text-fg"
          >
            Yenile
          </button>
        }
      />

      <div className="mt-3 flex items-end gap-5">
        <div>
          <p className="text-[11px] text-fg-subtle">Bu ay</p>
          <p className="num text-[20px] font-semibold tracking-[-0.02em] text-fg">{formatUsd(spend.ayUsd)}</p>
        </div>
        <div>
          <p className="text-[11px] text-fg-subtle">Bugün</p>
          <p className="num text-[14px] font-medium text-fg">{formatUsd(spend.bugunUsd)}</p>
        </div>
        <div>
          <p className="text-[11px] text-fg-subtle">İş</p>
          <p className="num text-[14px] font-medium text-fg">{spend.isSayisi}</p>
        </div>
      </div>

      {son30.length > 0 ? (
        <div className="mt-3 flex h-12 items-end gap-1" aria-hidden>
          {son30.map((g) => (
            <div
              key={g.gun}
              title={`${g.gun} · ${formatUsd(g.usd)}`}
              className="flex-1 rounded-t-[3px] bg-brand/70"
              style={{ height: `${Math.max(6, (g.usd / maks) * 100)}%` }}
            />
          ))}
        </div>
      ) : (
        <p className="mt-3 text-[11.5px] text-fg-subtle">Henüz maliyet kaydı yok. İşler bittikçe burada birikir.</p>
      )}

      {turler.length > 0 ? (
        <div className="mt-3 space-y-1 border-t border-border pt-2.5">
          {turler.map(([kind, usd]) => (
            <div key={kind} className="flex items-center justify-between text-[11.5px]">
              <span className="text-fg-muted">{KIND_LABEL[kind] ?? kind} ortalaması</span>
              <span className="num text-fg">{formatUsd(usd)}</span>
            </div>
          ))}
        </div>
      ) : null}

      {spend.son.length > 0 ? (
        <div className="mt-2.5 space-y-1 border-t border-border pt-2.5">
          {spend.son.slice(0, 4).map((k, i) => (
            <div key={`${k.t}-${i}`} className={cn('flex items-center justify-between gap-3 text-[11px]')}>
              <span className="truncate text-fg-subtle" title={k.baslik}>
                {k.baslik}
              </span>
              <span className="shrink-0 text-fg-subtle">
                <span className="num text-fg">{formatUsd(k.usd)}</span> · {formatRelative(k.t)}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  )
}
