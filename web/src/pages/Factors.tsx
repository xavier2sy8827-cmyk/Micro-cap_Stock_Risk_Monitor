import { useState } from 'react'
import { Heatmap, TimeSeries } from '../charts'
import { useJson } from '../lib/data'
import { fmt, lastNum, rangeStart } from '../lib/range'
import type { Factors } from '../lib/types'
import { useMeta } from '../meta'
import { ChartCard, ErrorBox, Loading, PageTitle } from '../ui'

export default function FactorsPage() {
  const meta = useMeta()
  const { data, error, loading } = useJson<Factors>('factors.json')
  const [sel, setSel] = useState('F1_SIZE')
  if (loading) return <Loading />
  if (error || !data) return <ErrorBox message={error ?? 'factors.json 缺失'} />
  const f = data
  const total = f.dates.length
  const hasFactors = Object.keys(f.states).length > 0
  const asof = f.updated_through ?? meta?.data_through ?? f.dates[total - 1]
  const labels = f.factors.map((k) => `${k.split('_')[0]} ${f.names[k] ?? k}`)
  const selected = f.factors.includes(sel) ? sel : f.factors[0]

  if (!hasFactors) {
    return (
      <>
        <PageTitle title="核心因子监控" desc={`数据截至 ${meta?.data_through ?? '—'}`} />
        <div className="hint">
          本数据集未包含因子（切片时跳过了 moneyflow 或历史不足 41 个交易日）。全量 INIT 后会生成。
        </div>
      </>
    )
  }

  return (
    <>
      <PageTitle
        title="核心因子监控"
        desc={`IC 截至 ${asof}（前瞻 20 日，尾部 ${f.tail_gap} 日不可判）· 数据 ${meta?.data_through ?? '—'}`}
      />

      <ChartCard
        title="四态热力"
        subtitle="0 健康 / 1 衰减 / 2 拥挤回撤 / 3 失效；空白 = 判据不可判（不显示为健康）"
        summary="越深 = 状态越差"
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <Heatmap
              names={labels}
              matrix={f.factors.map((k) =>
                f.states[k].state
                  .map((v, i) => (f.states[k].judge_nan[i] ? null : v))
                  .slice(s),
              )}
              dates={f.dates.slice(s)}
              height={220}
              max={3}
              colors={['#3ba272', '#c47f17', '#d5495c', '#805ad5']}
            />
          )
        }}
      </ChartCard>

      <div className="chips" role="group" aria-label="因子选择">
        {f.factors.map((k) => (
          <button key={k} type="button" className={k === selected ? 'chip on' : 'chip'} onClick={() => setSel(k)}>
            {k.split('_')[0]} {f.names[k] ?? ''}
          </button>
        ))}
      </div>

      <ChartCard
        title={`${selected.split('_')[0]} ${f.names[selected] ?? ''} · Rank IC`}
        subtitle="日频 Rank IC（浅）与 252 日均值（深）；IC 末日 = 数据末日 − 20"
        summary={`IC ${fmt(lastNum(f.ic[selected]), 3)}`}
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={f.dates.slice(s)}
              lines={[
                { label: 'Rank IC', values: f.ic[selected].slice(s), color: '#9ec5f0' },
                { label: 'IC 252 均值', values: f.ic_mean_252[selected].slice(s), color: '#2b6cb0' },
              ]}
              height={230}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title={`${selected.split('_')[0]} · 多空净值`}
        subtitle="五分位等权日调（Q5−Q1），加法净值；非可交易口径"
        summary={`NAV ${fmt(lastNum(f.ls_nav[selected]), 2)}`}
        asof={meta?.data_through}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={f.dates.slice(s)}
              lines={[{ label: '多空 NAV', values: f.ls_nav[selected].slice(s), color: '#d5495c' }]}
              height={230}
            />
          )
        }}
      </ChartCard>

      <ChartCard
        title="ICIR 与状态判据"
        subtitle="ICIR(252) 与判据灯（L/D/R/F）；NaN = 不可判"
        summary={`L ${fmt(lastNum(f.states[selected].L), 0)} · D ${fmt(lastNum(f.states[selected].D), 0)} · R ${fmt(lastNum(f.states[selected].R), 0)} · F ${fmt(lastNum(f.states[selected].F), 0)}`}
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={f.dates.slice(s)}
              lines={[{ label: 'ICIR', values: f.icir_252[selected].slice(s), color: '#805ad5' }]}
              height={200}
            />
          )
        }}
      </ChartCard>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>因子</th>
              <th>事件日</th>
              <th>确认日</th>
              <th>结束</th>
              <th>深度</th>
              <th>σ倍数</th>
              <th>天数</th>
            </tr>
          </thead>
          <tbody>
            {f.events.slice(-30).reverse().map((e, i) => (
              <tr key={`${e.factor}-${e.event_date}-${i}`}>
                <td>{e.factor.split('_')[0]}</td>
                <td>{e.event_date}</td>
                <td>{e.confirm_date ?? '—'}</td>
                <td>{e.end_date ?? '—'}</td>
                <td>{fmt(e.depth as number | null, 3)}</td>
                <td>{fmt(e.sigma_mult as number | null, 1)}</td>
                <td>{fmt(e.days as number | null, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="hint">
        预警事件共 {f.events.length} 条；只展示最近 30 条。R 首次触发后 10 个交易日内复现才确认，否则仅登记事件。
      </div>
    </>
  )
}
