import { useMemo, useState, type ReactNode } from 'react'
import { ListPlus, Play, Trash2, X } from 'lucide-react'
import { CHANNELS } from '@shared/channels'
import type { ChannelId, JobKind } from '@shared/types'
import { useApp, useGunSayisi } from '@/app/AppContext'
import { Badge, Button, Panel, SectionTitle, Select } from '@/components/ui/primitives'
import { formatRelative } from '@/lib/utils'

const DURUM_TONE = {
  bekliyor: 'neutral',
  calisiyor: 'brand',
  bitti: 'success',
  hata: 'danger',
  iptal: 'warn',
} as const

const DURUM_LABEL: Record<string, string> = {
  bekliyor: 'bekliyor',
  calisiyor: 'çalışıyor',
  bitti: 'bitti',
  hata: 'hata',
  iptal: 'iptal',
}

/**
 * Is kuyrugu: birden cok link yapistirip sirayla isleme. Kuyruk ana surecte
 * kalici tutulur (uygulama kapansa da kaybolmaz); bir is bitince ayarliysa
 * siradaki otomatik baslar.
 */
export function KuyrukPaneli(): ReactNode {
  const { queue, queueAdd, queueRemove, queueClear, queueStartNext, pushToast, settings, job } = useApp()
  const [gunSayisi] = useGunSayisi()
  const [metin, setMetin] = useState('')
  const [kind, setKind] = useState<JobKind>('channel')
  const [kanal, setKanal] = useState<ChannelId>('1')
  const [busy, setBusy] = useState(false)

  const linkler = useMemo(
    () =>
      metin
        .split(/[\r\n]+/)
        .map((s) => s.trim())
        .filter((s) => /^https?:\/\//i.test(s)),
    [metin],
  )

  const bekleyen = queue.filter((o) => o.status === 'bekliyor').length
  const calisan = queue.some((o) => o.status === 'calisiyor') || job?.status === 'running'
  const linkGerekli = kind === 'channel'

  const ekle = async (): Promise<void> => {
    if (linkGerekli && linkler.length === 0) {
      pushToast({ tone: 'warn', title: 'Link gerekli', message: 'Her satıra bir http(s) linki yapıştırın.' })
      return
    }
    const girdiler =
      linkler.length > 0
        ? linkler.map((link) => ({ kind, channelId: kanal, link, gunSayisi, haftalik: kind !== 'channel' }))
        : [{ kind, channelId: kanal, gunSayisi, haftalik: kind !== 'channel' }]
    setBusy(true)
    try {
      await queueAdd(girdiler)
      setMetin('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel className="p-4">
      <SectionTitle
        title="İş kuyruğu"
        subtitle="Birden çok linki sırayla işle (kalıcı)"
        icon={<ListPlus className="size-4" />}
        right={
          <div className="flex items-center gap-1.5">
            {bekleyen > 0 ? <Badge tone="brand">{bekleyen} bekliyor</Badge> : null}
            <Button size="sm" variant="ghost" icon={<Trash2 className="size-3.5" />} onClick={() => void queueClear()} disabled={queue.length === 0}>
              Temizle
            </Button>
          </div>
        }
      />

      <div className="mt-3 grid gap-2.5 lg:grid-cols-[1fr_170px_160px_auto] lg:items-end">
        <textarea
          value={metin}
          onChange={(e) => setMetin(e.target.value)}
          rows={2}
          placeholder={'Her satıra bir link yapıştır:\nhttps://youtu.be/...\nhttps://www.tiktok.com/...'}
          className="min-h-[62px] w-full resize-y rounded-[10px] border border-border bg-[var(--surface-2)] px-3 py-2 font-mono text-[11.5px] text-fg placeholder:text-fg-subtle focus:border-brand focus:outline-none"
        />
        <Select value={kind} onChange={(e) => setKind(e.target.value as JobKind)} aria-label="İş türü">
          <option value="channel">Kanal işlemi</option>
          <option value="discover">Keşif</option>
          <option value="weekly">Çok günlü zincir</option>
        </Select>
        <Select value={kanal} onChange={(e) => setKanal(e.target.value as ChannelId)} aria-label="Kanal">
          {CHANNELS.map((c) => (
            <option key={c.id} value={c.id}>
              {c.id} · {c.name}
            </option>
          ))}
        </Select>
        <Button
          variant="primary"
          loading={busy}
          icon={<ListPlus className="size-3.5" />}
          onClick={() => void ekle()}
          disabled={linkGerekli && linkler.length === 0}
        >
          Kuyruğa ekle
        </Button>
      </div>

      {linkler.length > 0 ? (
        <p className="mt-2 text-[11px] text-fg-subtle">
          {linkler.length} link algılandı · tür:{' '}
          {kind === 'channel' ? 'kanal işlemi' : kind === 'discover' ? 'keşif' : 'zincir'}
        </p>
      ) : null}

      {queue.length > 0 ? (
        <div className="mt-3 space-y-1.5 border-t border-border pt-3">
          {queue.map((o) => (
            <div key={o.id} className="flex items-center gap-2.5 rounded-[9px] border border-border bg-[var(--surface-2)] px-2.5 py-2">
              <Badge tone={DURUM_TONE[o.status]} dot={o.status === 'calisiyor'}>
                {DURUM_LABEL[o.status] ?? o.status}
              </Badge>
              <span className="truncate text-[11.5px] text-fg" title={o.title}>
                {o.title}
              </span>
              <span className="ml-auto shrink-0 text-[10.5px] text-fg-subtle">{formatRelative(o.addedAt)}</span>
              <button
                onClick={() => void queueRemove(o.id)}
                disabled={o.status === 'calisiyor'}
                title="Kuyruktan çıkar"
                className="grid size-6 shrink-0 place-items-center rounded-[6px] text-fg-subtle transition-colors hover:bg-[var(--surface-3)] hover:text-fg disabled:opacity-30"
              >
                <X className="size-3.5" />
              </button>
            </div>
          ))}
          {!calisan && bekleyen > 0 ? (
            <div className="pt-1">
              <Button size="sm" variant="secondary" icon={<Play className="size-3.5" />} loading={busy} onClick={() => void queueStartNext()}>
                Sıradakini şimdi başlat
              </Button>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 border-t border-border pt-3 text-[11.5px] text-fg-subtle">
          Kuyruk boş. Link yapıştırıp ekleyince sırayla işlenir
          {settings?.queueAutoStart ? ' (otomatik başlatma açık)' : ' (otomatik başlatma kapalı)'}.
        </p>
      )}
    </Panel>
  )
}
