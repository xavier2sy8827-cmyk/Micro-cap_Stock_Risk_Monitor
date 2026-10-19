import { TimeSeries } from '../charts'
import { useJson } from '../lib/data'
import { fmt, fmtPct, lastNum, rangeStart } from '../lib/range'
import type { Margin } from '../lib/types'
import { useMeta } from '../meta'
import { ChartCard, ErrorBox, Loading, PageTitle } from '../ui'

export default function MarginPage() {
  const meta = useMeta()
  const { data, error, loading } = useJson<Margin>('margin.json')
  if (loading) return <Loading />
  if (error || !data) return <ErrorBox message={error ?? 'margin.json 缺失'} />
  const m = data
  const total = m.dates.length
  const hasData = m.ratio.some((v) => v !== null)
  const through = m.through ?? meta?.margin_through ?? '—'

  if (!hasData) {
    return (
      <>
        <PageTitle title="两融" desc="当前切片未含两融数据" />
        <div className="hint">本切片以 `--no-margin` 运行；全量 INIT 后会补齐 circ-1000 口径。</div>
      </>
    )
  }

  return (
    <>
      <PageTitle
        title="两融"
        desc={`主口径 circ-1000（与旧 notebook 一致）· 数据截至 ${through}（T-1 发布）`}
      />

      <ChartCard
        title="融资余额占比 margin_pool_ratio"
        subtitle="池内融资余额 / 全市场融资余额；circ-1000 池"
        summary={`${fmt(lastNum(m.ratio), 3, '%')} · 池内 ${fmt(lastNum(m.n), 0)} 只`}
        asof={through}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={m.dates.slice(s)}
              lines={[{ label: '占比', values: m.ratio.slice(s), color: '#2b6cb0' }]}
              height={230}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="90 日滚动标准化 z"
        subtitle="（占比 − 90 日均值）/ 90 日标准差；±2 为警戒"
        summary={`z ${fmt(lastNum(m.ratio_z), 2)}`}
        asof={through}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={m.dates.slice(s)}
              lines={[{ label: 'z', values: m.ratio_z.slice(s), color: '#c47f17' }]}
              height={210}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="融资买入额占比"
        subtitle="池内融资买入额 / 全市场融资买入额"
        summary={fmtPct(lastNum(m.buy_ratio), 2)}
        asof={through}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={m.dates.slice(s)}
              lines={[{ label: '买入占比', values: m.buy_ratio.slice(s), color: '#3ba272' }]}
              height={220}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="池内两融标的数"
        subtitle="<200 时占比指标统计意义弱，只做观察"
        summary={`${fmt(lastNum(m.n), 0)} 只`}
        asof={through}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={m.dates.slice(s)}
              lines={[{ label: '标的数', values: m.n.slice(s), color: '#805ad5' }]}
              height={200}
            />
          )
        }}
      </ChartCard>

      <div className="hint">
        wp400 观察列：占比 {fmtPct(lastNum(m.wp400_ratio), 3)}、标的 {fmt(lastNum(m.wp400_n), 0)} 只；低覆盖，不进阈值。
        两融为 T-1 发布，最新交易日可能尚未落库，次日运行会回填该行。
      </div>
    </>
  )
}
