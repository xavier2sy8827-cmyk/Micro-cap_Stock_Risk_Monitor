import { Sparkline } from '../charts'
import { useJson } from '../lib/data'
import { fmt, fmtPct } from '../lib/range'
import type { Overview as OverviewData } from '../lib/types'
import { useMeta } from '../meta'
import { ErrorBox, Loading, PageTitle } from '../ui'

const SPARK_COLOR: Record<string, string> = {
  breadth10: '#2b6cb0',
  pb_spread: '#d5495c',
  corr60_wp400: '#805ad5',
  ls_vol_ratio: '#c47f17',
  qs_share: '#3ba272',
}

export default function Overview() {
  const meta = useMeta()
  const { data, error, loading } = useJson<OverviewData>('overview.json')

  if (loading) return <Loading />
  if (error || !data) return <ErrorBox message={error ?? 'overview.json 缺失'} />

  const spark = new Map(data.spark.series.map((s) => [s.key, s.values]))

  return (
    <>
      <PageTitle
        title="监控总览"
        desc={`数据截至 ${meta?.data_through ?? '—'} · 两融 ${meta?.margin_through ?? '—'} · 行业 ${meta?.industry_version ?? '—'}`}
      />

      <div className="sig-grid">
        {data.signals.map((s) => (
          <div className={`sig lv-${s.level}`} key={s.key}>
            <div className="sig-lab">{s.label}</div>
            <div className="sig-val">
              {fmt(s.value, s.key === 'corr60_wp400' || s.key === 'ls_vol_ratio' ? 3 : 2, s.unit)}
            </div>
            <div className="sig-sub">
              {s.pct !== null && s.pct !== undefined ? `分位 ${fmtPct(s.pct)}` : ''}
              {s.z !== null && s.z !== undefined ? ` z ${fmt(s.z, 1)}` : ''}
              {s.asof ? ` · ${s.asof}` : ''}
            </div>
            {spark.get(s.key) ? <Sparkline values={spark.get(s.key) ?? []} color={SPARK_COLOR[s.key]} /> : null}
          </div>
        ))}
      </div>

      <div className="hint">
        图默认折叠：点底部页签进入详情，点开图卡后再选显示范围（默认 52 周）。指标口径与 asof 见「更多 → 关于」。
      </div>

      <div className="note">
        <h2>当前状态说明</h2>
        <ul>
          <li>宽度分位低 = 池内跌破 MA20 的比例高，属“冰点”而非健康。</li>
          <li>PB 价差 / 截面相关 / 多空波动比同时高位，才是拥挤共振。</li>
          <li>两融数据为 T-1 发布，最新日通常比行情晚一天。</li>
          <li>因子四态（失效/衰减/回撤/转负）在「因子」页，IC 尾部 20 日因前瞻收益不足显示为空白。</li>
        </ul>
      </div>
    </>
  )
}
