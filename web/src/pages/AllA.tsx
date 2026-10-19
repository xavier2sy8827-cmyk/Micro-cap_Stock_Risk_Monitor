import { Heatmap, TimeSeries } from '../charts'
import { useJson } from '../lib/data'
import { fmt, lastNum, rangeStart } from '../lib/range'
import type { AllA } from '../lib/types'
import { useMeta } from '../meta'
import { ChartCard, ErrorBox, Loading, PageTitle } from '../ui'

const LAYER_COLORS: Record<string, string> = {
  '300': '#2b6cb0',
  '500': '#3ba272',
  '1000': '#805ad5',
  '2000': '#c47f17',
  wp400: '#d5495c',
}

export default function AllAPage() {
  const meta = useMeta()
  const { data, error, loading } = useJson<AllA>('alla.json')
  if (loading) return <Loading />
  if (error || !data) return <ErrorBox message={error ?? 'alla.json 缺失'} />
  const a = data
  const total = a.dates.length
  const asof = meta?.data_through ?? a.dates[total - 1]

  return (
    <>
      <PageTitle title="全A结构" desc={`数据截至 ${asof} · 行业 ${meta?.industry_version ?? '—'} · 图默认收起`} />

      <ChartCard
        title="申万一级行业扩散热力"
        subtitle="各行业 close>MA20 占比；按行业版本切换 28/31 个一级行业"
        summary={`最新 ${fmt(lastNum(a.s_width_pct), 1, '%')}`}
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <Heatmap
              names={a.industries.names}
              matrix={a.industries.matrix.map((row) => row.slice(s))}
              dates={a.dates.slice(s)}
              height={Math.max(320, a.industries.names.length * 15 + 50)}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="S 宽度"
        subtitle="各行业扩散率（整数）加总；跨版本看 s_width_pct"
        summary={`${fmt(lastNum(a.s_width), 0)} · ${fmt(lastNum(a.s_width_pct), 1, '%')}`}
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={a.dates.slice(s)}
              lines={[{ label: 'S 宽度', values: a.s_width.slice(s), color: '#2b6cb0' }]}
              height={220}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="成交额集中度 top5% / top10%"
        subtitle="全A剔北交所；前 X% 只数 = max(1, round(当日有效只数 × X%))"
        summary={`${fmt(lastNum(a.top5.v), 1, '%')} / ${fmt(lastNum(a.top10.v), 1, '%')}`}
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={a.dates.slice(s)}
              lines={[
                { label: 'top5%', values: a.top5.v.slice(s), color: '#d5495c' },
                { label: 'top10%', values: a.top10.v.slice(s), color: '#2b6cb0' },
              ]}
              pct={a.top5.pct ? a.top5.pct.slice(s) : undefined}
              height={240}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="五层成交额占比分位"
        subtitle="各层成交额占比的 250 日滚动分位；90/10 为高低线（与 notebook 模块③一致）"
        summary={`微盘400 分位 ${fmt(lastNum(a.five_layer.share_pct.wp400), 0)} · 占比 ${fmt(lastNum(a.five_layer.share.wp400), 2, '%')}`}
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={a.dates.slice(s)}
              lines={a.five_layer.names.map((n) => ({
                label: n === 'wp400' ? '微盘400' : n,
                values: a.five_layer.share_pct[n].slice(s),
                color: LAYER_COLORS[n],
              }))}
              thresholds={[90, 10]}
              height={260}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="各层收益率 MA5"
        subtitle="指数层用指数收盘收益；微盘400 用池等权收益；单位 %/日"
        summary=""
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={a.dates.slice(s)}
              lines={a.five_layer.names.map((n) => ({
                label: n === 'wp400' ? '微盘400' : n,
                values: a.five_layer.ret_ma5[n].slice(s),
                color: LAYER_COLORS[n],
              }))}
              height={260}
            />
          )
        }}
      </ChartCard>
    </>
  )
}
