import { dataUrl } from './data'

const DEFAULT_ENDPOINT = 'https://wp-refresh.xavier-wp.workers.dev'
const ENDPOINT = ((import.meta.env.VITE_REFRESH_ENDPOINT as string | undefined) || DEFAULT_ENDPOINT).replace(/\/+$/, '')

export const refreshEnabled = !!ENDPOINT

export interface RefreshRun {
  status: string
  conclusion: string | null
  created_at: string
  html_url: string
}

export interface RefreshStatus {
  ok: boolean
  active: boolean
  dispatched_at: string | null
  run: RefreshRun | null
  last_data_through: string | null
  last_generated_at: string | null
}

export interface TriggerResult {
  status: number
  body: Record<string, unknown>
}

export async function getRefreshStatus(): Promise<RefreshStatus> {
  if (!ENDPOINT) throw new Error('refresh endpoint not configured')
  const r = await fetch(`${ENDPOINT}/status`, { cache: 'no-store' })
  if (!r.ok) throw new Error(`status HTTP ${r.status}`)
  return (await r.json()) as RefreshStatus
}

export async function triggerRefresh(key?: string): Promise<TriggerResult> {
  if (!ENDPOINT) throw new Error('refresh endpoint not configured')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (key) headers['X-Refresh-Key'] = key
  const r = await fetch(`${ENDPOINT}/refresh`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ref: 'main' }),
    cache: 'no-store',
  })
  let body: Record<string, unknown> = {}
  try {
    body = (await r.json()) as Record<string, unknown>
  } catch {
    body = {}
  }
  return { status: r.status, body }
}

export function readRefreshKey(): string {
  try {
    return localStorage.getItem('wp-refresh-key') ?? ''
  } catch {
    return ''
  }
}

export function saveRefreshKey(key: string): void {
  try {
    localStorage.setItem('wp-refresh-key', key)
  } catch {
    /* ignore */
  }
}

export async function waitForPages(target: string, onWait: (text: string) => void): Promise<void> {
  const deadline = Date.now() + 10 * 60 * 1000
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`${dataUrl('meta.json')}?v=${Date.now()}`, { cache: 'no-cache' })
      if (r.ok) {
        const m = (await r.json()) as { data_through?: string }
        if (m.data_through && m.data_through >= target) {
          const u = new URL(window.location.href)
          u.searchParams.set('v', m.data_through)
          window.location.replace(u.toString())
          return
        }
      }
    } catch {
      /* retry */
    }
    onWait('服务端已更新，CDN 同步中…')
    await new Promise((r) => setTimeout(r, 15000))
  }
  onWait('数据已更新，请稍后手动刷新')
}
