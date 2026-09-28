import { useCallback, useEffect, useRef, useState } from 'react'

export interface Resource<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Basit veri yukleyici: ilk yukleme + manuel yenileme + opsiyonel periyodik tazeleme. */
export function useResource<T>(
  loader: () => Promise<T>,
  deps: unknown[] = [],
  options: { intervalMs?: number; enabled?: boolean } = {},
): Resource<T> {
  const { intervalMs = 0, enabled = true } = options
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const mounted = useRef(true)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  const run = useCallback(async () => {
    setLoading(true)
    try {
      const result = await loaderRef.current()
      if (mounted.current) {
        setData(result)
        setError(null)
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (mounted.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    if (!enabled) return () => {
      mounted.current = false
    }
    void run()
    return () => {
      mounted.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, run, ...deps])

  useEffect(() => {
    if (!intervalMs || !enabled) return
    const id = window.setInterval(() => void run(), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs, enabled, run])

  return { data, error, loading, reload: () => void run() }
}

/** Otomatik kayan konteyner icin: yeni satir gelince en alta in. */
export function useAutoScroll<T extends HTMLElement>(dep: unknown, enabled = true): React.RefObject<T | null> {
  const ref = useRef<T | null>(null)
  const stick = useRef(true)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onScroll = (): void => {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
      stick.current = atBottom
    }
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const el = ref.current
    if (!el || !enabled || !stick.current) return
    el.scrollTop = el.scrollHeight
  }, [dep, enabled])

  return ref
}

/** Her saniye tazelenen zaman damgasi (sure gostergesi icin). */
export function useTicker(active: boolean): number {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setTick((t) => t + 1), 1000)
    return () => window.clearInterval(id)
  }, [active])
  return tick
}

export function useCopy(): [string | null, (text: string) => void] {
  const [copied, setCopied] = useState<string | null>(null)
  const copy = useCallback((text: string) => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(text)
      window.setTimeout(() => setCopied(null), 1500)
    })
  }, [])
  return [copied, copy]
}
