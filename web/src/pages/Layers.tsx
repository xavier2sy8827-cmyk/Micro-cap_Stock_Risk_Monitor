import { Heatmap, TimeSeries } from '../charts'
import { useJson } from '../lib/data'
import { fmt, fmtPct, lastNum, rangeStart } from '../lib/range'
import type { Layers } from '../lib/types'
import { useMeta } from '../meta'
import { ChartCard, ErrorBox, Loading, PageTitle } from '../ui'

const COLORS = [
  '#2b6cb0',
  '#3ba272',
  '#805ad5',
  '#c47f17',
  '#d5495c',
  '#4a5568',
  '#2c7a7b',
  '#b83280',
  '#6b46c1',
  '#975a16',
]

export default function LayersPage() {
  const meta = useMeta()
  const { data, error, loading } = useJson<Layers>('layers.json')
  if (loading) return <Loading />
  if (error || !data) return <ErrorBox message={error ?? 'layers.json 缺失'} />
  const l = data
  const total = l.dates.length
  const asof = meta?.data_through ?? l.dates[total - 1]
  const names = l.layers.map((x) => x.key)

  return (
    <>
      <PageTitle title="微盘内部 10 层" desc={`L1=总市值最小 40 只，L10=最大 40 只 · 数据截至 ${asof}`} />

      <ChartCard
        title="各层扩散分位"
        subtitle="层内 close>MA20(不含当日) 占比的 250 日滚动分位；n<30 记空"
        summary="热力越红 = 该层越热"
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <Heatmap
              names={names}
              matrix={l.layers.map((x) => x.pct.slice(s))}
              dates={l.dates.slice(s)}
              height={260}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="各层收益率 MA5"
        subtitle="层内等权日收益的 5 日均值；单位 %/日"
        summary="哪一层在赚钱"
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={l.dates.slice(s)}
              lines={l.layers.map((x, i) => ({
                label: x.key,
                values: x.ret_ma5.slice(s),
                color: COLORS[i],
              }))}
              height={280}
            />
          )
        }}
      </ChartCard>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>层</th>
              <th>最新宽度</th>
              <th>分位</th>
              <th>收益 MA5</th>
              <th>有效成员</th>
            </tr>
          </thead>
          <tbody>
            {l.layers.map((x) => (
              <tr key={x.key}>
                <td>{x.key}</td>
                <td>{fmt(lastNum(x.breadth), 1, '%')}</td>
                <td>{fmtPct(lastNum(x.pct))}</td>
                <td>{fmt(lastNum(x.ret_ma5), 2, '%')}</td>
                <td>{fmt(lastNum(x.n_valid), 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
