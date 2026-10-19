import { Link } from 'react-router-dom'
import { useMeta } from '../meta'
import { PageTitle } from '../ui'

export default function FactorsPage() {
  const meta = useMeta()
  return (
    <>
      <PageTitle title="核心因子监控" desc={`M3 接入 · 当前数据截至 ${meta?.data_through ?? '—'}`} />
      <div className="hint">
        5 因子（SIZE / DIV / AMPL / INTRA_REV / RESID_REV）的 IC、多空衰减与四态，将在 M3 接入。
        四态：0 健康 / 1 衰减 / 2 拥挤回撤 / 3 失效；尾部 20 个交易日因前瞻收益未实现，判据不可判。
      </div>
      <div className="linkrow">
        <Link to="/more">返回更多</Link>
      </div>
    </>
  )
}
