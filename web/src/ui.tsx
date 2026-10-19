import { type ReactNode, useState } from 'react'
import { DEFAULT_RANGE, RANGES, type RangeKey } from './lib/range'

interface ChartCardProps {
  title: string
  subtitle?: string
  summary?: string
  asof?: string | null
  children: (range: RangeKey) => ReactNode
  defaultOpen?: boolean
}

const RANGE_KEY = 'wp-range'

function readRange(): RangeKey {
  try {
    const v = localStorage.getItem(RANGE_KEY)
    if (RANGES.some((r) => r.key === v)) return v as RangeKey
  } catch {
    /* ignore */
  }
  return DEFAULT_RANGE
}

export function ChartCard({ title, subtitle, summary, asof, children, defaultOpen = false }: ChartCardProps) {
  const forceOpen =
    typeof window !== 'undefined' &&
    `${window.location.search}${window.location.hash}`.includes('open=1')
  const [open, setOpen] = useState(defaultOpen || forceOpen)
  const [range, setRange] = useState<RangeKey>(() => readRange())

  const pick = (k: RangeKey) => {
    setRange(k)
    try {
      localStorage.setItem(RANGE_KEY, k)
    } catch {
      /* ignore */
    }
  }

  return (
    <section className={open ? 'cc open' : 'cc'}>
      <button className="cc-head" type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="cc-left">
          <span className="cc-title">{title}</span>
          {subtitle ? <span className="cc-sub">{subtitle}</span> : null}
        </span>
        <span className="cc-right">
          {summary ? <span className="cc-sum">{summary}</span> : null}
          {asof ? <span className="cc-asof">{asof}</span> : null}
          <span className="cc-chev" aria-hidden="true">
            {open ? '▾' : '▸'}
          </span>
        </span>
      </button>
      {open ? (
        <div className="cc-body">
          <div className="chips" role="group" aria-label="显示范围">
            {RANGES.map((r) => (
              <button
                key={r.key}
                type="button"
                className={r.key === range ? 'chip on' : 'chip'}
                onClick={() => pick(r.key)}
              >
                {r.key}
              </button>
            ))}
          </div>
          {children(range)}
        </div>
      ) : null}
    </section>
  )
}

export function Loading({ text = '加载数据…' }: { text?: string }) {
  return <div className="state">{text}</div>
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="errbox">
      <strong>数据加载失败</strong>
      <span>{message}</span>
    </div>
  )
}

export function PageTitle({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="page-title">
      <h2>{title}</h2>
      {desc ? <p>{desc}</p> : null}
    </div>
  )
}
