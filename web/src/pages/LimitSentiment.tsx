import { TimeSeries } from '../charts'
import { useJson } from '../lib/data'
import { fmt, fmtPct, rangeStart } from '../lib/range'
import type { LimitSentiment, LimitSentimentRow, Num } from '../lib/types'
import { ChartCard, ErrorBox, Loading, PageTitle } from '../ui'

const UNIVERSES = [
  { key: 'main', name: '主板', color: '#2b6cb0' },
  { key: 'wp400', name: '微盘400', color: '#c47f17' },
  { key: 'gem', name: '创业板', color: '#3ba272' },
]

function metric(row: LimitSentimentRow, key: string): Num {
  const value = row[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function signed(value: Num, digits = 2): string {
  if (value === null) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

function height(row: LimitSentimentRow): string {
  return `${fmt(metric(row, 'max_height'), 0)}板（${fmtPct(metric(row, 'max_height_pct'))}）`
}

function promotions(row: LimitSentimentRow): string {
  return ['promote_1_2', 'promote_2_3', 'promote_3p']
    .map((key) => fmtPct(metric(row, key), 1))
    .join(' / ')
}

export default function LimitSentimentPage() {
  const { data, error, loading } = useJson<LimitSentiment>('limit_sentiment.json')
  if (loading) return <Loading />
  if (error || !data) return <ErrorBox message={error ?? 'limit_sentiment.json 缺失'} />

  const rows = new Map(data.latest.map((row) => [row.universe, row]))
  const total = data.dates.length
  const main = rows.get('main')

  return (
    <>
      <PageTitle
        title="涨停情绪监控"
        desc={`GitHub Action 盘后更新 · 数据截至 ${data.through ?? '—'}`}
      />

      {data.latest.length === 0 ? (
        <div className="warnbox">等待首次盘后涨停情绪更新；现有其他监控不受影响。</div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="table" aria-label="涨停情绪当日快照">
              <thead>
                <tr>
                  <th>市场</th>
                  <th>最高板（分位）</th>
                  <th>宽度 1/2/3/4/5+</th>
                  <th>晋级率 1→2 / 2→3 / 3+</th>
                  <th>断板收益 均值/中位</th>
                  <th>昨停溢价 开盘/收盘</th>
                  <th>炸板率</th>
                  <th>跌停</th>
                </tr>
              </thead>
              <tbody>
                {UNIVERSES.map(({ key, name }) => {
                  const row = rows.get(key)
                  if (!row) return null
                  const width = ['width_1', 'width_2', 'width_3', 'width_4', 'width_5p']
                    .map((field) => fmt(metric(row, field), 0))
                    .join('/')
                  const broken = `${signed(metric(row, 'broken_close_mean'))}/${signed(metric(row, 'broken_close_median'))}`
                  const premium = `${signed(metric(row, 'prev_limit_open_mean'))}/${signed(metric(row, 'prev_limit_close_mean'))}`
                  return (
                    <tr key={key}>
                      <td>{name}</td>
                      <td>{height(row)}</td>
                      <td>{width}</td>
                      <td>{promotions(row)}</td>
                      <td>{broken}</td>
                      <td>{premium}</td>
                      <td>{fmtPct(metric(row, 'failed_rate'), 1)}</td>
                      <td>{fmt(metric(row, 'limit_down_n'), 0)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="hint">日期：{main?.asof ?? data.through ?? '—'} · 仅展示盘后事实，不输出情绪评分或离场建议。</div>
        </>
      )}

      {total > 0 ? (
        <ChartCard
          title="连板高度"
          subtitle="各市场当日最高收盘连板数；250 日滚动分位见当日快照"
          summary={main ? `主板 ${height(main)}` : '—'}
          asof={data.through}
          defaultOpen
        >
          {(range) => {
            const start = rangeStart(total, range)
            return (
              <TimeSeries
                dates={data.dates.slice(start)}
                lines={UNIVERSES.filter(({ key }) => data.height[key]).map(({ key, name, color }) => ({
                  label: name,
                  values: data.height[key].slice(start),
                  color,
                }))}
                height={230}
              />
            )
          }}
        </ChartCard>
      ) : null}

      {data.latest.length > 0 ? (
        <div className="note">
          <h2>样本与口径</h2>
          <ul>
            {UNIVERSES.map(({ key, name }) => {
              const row = rows.get(key)
              if (!row) return null
              const samples = ['promote_1_2', 'promote_2_3', 'promote_3p']
                .map((field, index) => {
                  const labels = ['1→2', '2→3', '3+']
                  return `${labels[index]} ${fmt(metric(row, `${field}_num`), 0)}/${fmt(metric(row, `${field}_den`), 0)}`
                })
                .join('，')
              return (
                <li key={key}>
                  {name}：涨停 {fmt(metric(row, 'limit_up_n'), 0)} 只；断板样本 {fmt(metric(row, 'broken_return_n'), 0)}/{fmt(metric(row, 'broken_n'), 0)}；晋级 {samples}
                </li>
              )
            })}
            <li>炸板率为日线“触及涨停但未封收”的代理口径；晋级与断板均使用昨日固定 cohort。</li>
          </ul>
        </div>
      ) : null}
    </>
  )
}
