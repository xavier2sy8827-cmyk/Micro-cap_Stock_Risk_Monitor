import { useMeta } from '../meta'
import { PageTitle } from '../ui'

export default function AboutPage() {
  const meta = useMeta()
  const full = (meta?.days ?? 0) > 1000
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
          <li>更新方式：`data` 分支 + 每个交易日 17:00 GitHub Actions 增量</li>
        </ul>
      </div>

      <div className="note">
        <h2>当前限制</h2>
        <ul>
          {full ? (
            <li>全量数据从 2016-01-04 起；2016 年初的分位、IC 均值、756 日判据仍在预热，空白属正常。</li>
          ) : (
            <li>当前是近端切片（少于 1000 个交易日），不是 2016 起全量；全量 INIT 替换后此提示消失。</li>
          )}
          <li>图默认 52 周；分位为 250 日滚动，早期窗口为空属预热。</li>
          <li>因子 IC 使用 20 日前瞻收益，最后 20 个交易日不可判，页面留空而不是显示“健康”。</li>
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
        <h2>二期（不做）</h2>
        <ul>
          <li>IM 贴水、宏观/信用利差、估值页</li>
          <li>盘中刷新、选股/持仓/组合</li>
        </ul>
      </div>
    </>
  )
}
