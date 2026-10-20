import type { Num } from './types'

export const RANGES = [
  { key: '4W', n: 20 },
  { key: '12W', n: 60 },
  { key: '26W', n: 130 },
  { key: '52W', n: 260 },
  { key: '1Y', n: 252 },
  { key: '2Y', n: 520 },
  { key: '5Y', n: 1300 },
  { key: 'ALL', n: 0 },
] as const

export type RangeKey = (typeof RANGES)[number]['key']
export const DEFAULT_RANGE: RangeKey = '4W'

export function rangeCount(range: RangeKey): number {
  return RANGES.find((r) => r.key === range)?.n ?? 0
}

/** 返回窗口起点（含）；图表都按“最近 n 个点”截取。 */
export function rangeStart(len: number, range: RangeKey): number {
  const n = rangeCount(range)
  return n > 0 ? Math.max(0, len - n) : 0
}

export function windowOf<T>(arr: T[], len: number, range: RangeKey): T[] {
  return arr.slice(rangeStart(len, range))
}

export function lastNum(arr: Num[] | undefined): Num {
  if (!arr) return null
  for (let i = arr.length - 1; i >= 0; i -= 1) {
    if (arr[i] !== null && Number.isFinite(arr[i] as number)) return arr[i]
  }
  return null
}

export function fmt(v: Num, digits = 2, suffix = ''): string {
  if (v === null || v === undefined || !Number.isFinite(v as number)) return '—'
  return `${(v as number).toFixed(digits)}${suffix}`
}

export function fmtPct(v: Num, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v as number)) return '—'
  return `${(v as number).toFixed(digits)}%`
}
