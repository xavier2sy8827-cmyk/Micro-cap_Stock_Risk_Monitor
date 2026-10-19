import { useMeta } from '../meta'
import { PageTitle } from '../ui'

export default function AboutPage() {
  const meta = useMeta()
  return (
    <>
      <PageTitle title="关于" desc="口径、数据状态与二期说明" />

      <div className="note">
        <h2>数据状态</h2>
        <ul>
          <li>数据源：Tushare Pro（仅 `TUSHARE_TOKEN`，不依赖本地数据库）</li>
          <li>数据截至：{meta?.data_through ?? '—'}</li>
          <li>两融截至：{meta?.margin_through ?? '（本切片未含）'}</li>
          <li>行业版本：{meta?.industry_version ?? '—'}</li>
          <li>交易日数：{meta?.days ?? '—'}</li>
          <li>生成时间：{meta?.generated_at ?? '—'}</li>
        </ul>
      </div>

      <div className="note">
        <h2>当前限制</h2>
        <ul>
          <li>本版是近端切片（约 2 年），不是 2016 起全量；全量 INIT 在 M4 完成后替换。</li>
          <li>因子四态、两融（若切片未含）、5 年分位在切片阶段可能为空或不完整。</li>
          <li>图默认 52 周；分位为 250 日滚动，早期窗口为空属预热。</li>
        </ul>
      </div>

      {meta && meta.warnings.length > 0 ? (
        <div className="warnbox">
          <strong>数据警告</strong>
          <ul>
            {meta.warnings.slice(-8).map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="note">
        <h2>二期</h2>
        <ul>
          <li>因子四态与事件表（M3）</li>
          <li>全量 2016 起 INIT 与每日 cron（M4/M5）</li>
          <li>盘中刷新、IM、估值与宏观分类</li>
        </ul>
      </div>
    </>
  )
}
