import type { ReactNode } from 'react'
import { TimeSeries } from '../charts'
import { useJson } from '../lib/data'
import { fmt, fmtPct, lastNum, rangeStart } from '../lib/range'
import type { Crowding } from '../lib/types'
import { useMeta } from '../meta'
import { ChartCard, ErrorBox, Loading, PageTitle } from '../ui'

function win<T>(arr: T[], start: number): T[] {
  return arr.slice(start)
}

export default function CrowdingPage() {
  const meta = useMeta()
  const { data, error, loading } = useJson<Crowding>('crowding.json')
  if (loading) return <Loading />
  if (error || !data) return <ErrorBox message={error ?? 'crowding.json 缺失'} />
  const c = data
  const total = c.dates.length
  const asof = meta?.data_through ?? c.dates[c.dates.length - 1]

  const card = (
    title: string,
    subtitle: string,
    value: number | null,
    pct: number | null,
    unit: string,
    render: (s: number) => ReactNode,
  ) => (
    <ChartCard
      title={title}
      subtitle={subtitle}
      summary={`${fmt(value, unit === '%' ? 2 : 3, unit)} · 分位 ${fmtPct(pct)}`}
      asof={asof}
    >
      {(r) => {
        const s = rangeStart(total, r)
        return render(s)
      }}
    </ChartCard>
  )

  return (
    <>
      <PageTitle title="拥挤度" desc={`数据截至 ${asof} · 图默认收起，52 周`} />
      <div className="hint">分位为 250 日滚动（蓝实线）；紫虚线为全样本 expanding 分位。</div>

      {card(
        '微盘400 宽度',
        '池内 close > MA20(含当日) 占比；分位=250日滚动',
        lastNum(c.breadth10.v),
        lastNum(c.breadth10.pct),
        '%',
        (s) => (
          <TimeSeries
            dates={win(c.dates, s)}
            lines={[{ label: '宽度', values: win(c.breadth10.v, s), color: '#2b6cb0' }]}
            pct={c.breadth10.pct ? win(c.breadth10.pct, s) : undefined}
            pctExp={c.breadth10.pct_exp ? win(c.breadth10.pct_exp, s) : undefined}
            thresholds={[20, 80]}
            height={250}
          />
        ),
      )}

      {card(
        'PB 价差（小/大 20%）',
        '全A按总市值两端各 20%，组内 pb>0 中位数之比；剔北交所',
        lastNum(c.pb_spread.v),
        lastNum(c.pb_spread.pct),
        '倍',
        (s) => (
          <TimeSeries
            dates={win(c.dates, s)}
            lines={[{ label: 'pb_spread', values: win(c.pb_spread.v, s), color: '#d5495c' }]}
            pct={c.pb_spread.pct ? win(c.pb_spread.pct, s) : undefined}
            pctExp={c.pb_spread.pct_exp ? win(c.pb_spread.pct_exp, s) : undefined}
            thresholds={[80, 90]}
            height={250}
          />
        ),
      )}

      {card(
        '截面相关性 corr60',
        '池内日收益两两 60 日相关系数均值；剔除 NaN/零方差，n<30 记空',
        lastNum(c.corr60_wp400.v),
        lastNum(c.corr60_wp400.pct),
        '',
        (s) => (
          <TimeSeries
            dates={win(c.dates, s)}
            lines={[{ label: 'corr60', values: win(c.corr60_wp400.v, s), color: '#805ad5' }]}
            pct={c.corr60_wp400.pct ? win(c.corr60_wp400.pct, s) : undefined}
            pctExp={c.corr60_wp400.pct_exp ? win(c.corr60_wp400.pct_exp, s) : undefined}
            thresholds={[85]}
            height={250}
          />
        ),
      )}

      {card(
        '多空波动比 ls_vol',
        '（微盘400 等权多 − 全A等权空）20 日年化波动 / 全A 年化波动',
        lastNum(c.ls_vol_ratio.v),
        lastNum(c.ls_vol_ratio.pct),
        '',
        (s) => (
          <TimeSeries
            dates={win(c.dates, s)}
            lines={[{ label: 'ls_vol', values: win(c.ls_vol_ratio.v, s), color: '#c47f17' }]}
            pct={c.ls_vol_ratio.pct ? win(c.ls_vol_ratio.pct, s) : undefined}
            pctExp={c.ls_vol_ratio.pct_exp ? win(c.ls_vol_ratio.pct_exp, s) : undefined}
            thresholds={[90]}
            height={250}
          />
        ),
      )}

      <ChartCard
        title="量化成交额占比 qs_share"
        subtitle="池内 money 分位<40% 且换手分位>60% 的子集；绝对值版作对照"
        summary={`${fmt(lastNum(c.qs.v), 2, '%')} · 有效成员 ${fmt(lastNum(c.qs.valid_n), 0)}`}
        asof={asof}
      >
        {(r) => {
          const s = rangeStart(total, r)
          return (
            <TimeSeries
              dates={win(c.dates, s)}
              lines={[
                { label: '分位口径', values: win(c.qs.v, s), color: '#3ba272' },
                { label: '绝对值对照', values: win(c.qs.abs, s), color: '#8a8a90', dashed: true },
              ]}
              pct={c.qs.pct ? win(c.qs.pct, s) : undefined}
              pctExp={c.qs.pct_exp ? win(c.qs.pct_exp, s) : undefined}
              height={270}
            />
          )
        }}
      </ChartCard>
    </>
  )
}
