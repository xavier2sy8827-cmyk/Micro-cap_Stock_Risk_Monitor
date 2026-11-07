import { Link } from 'react-router-dom'
import { useMeta } from '../meta'
import { PageTitle } from '../ui'

export default function MorePage() {
  const meta = useMeta()
  return (
    <>
      <PageTitle title="更多" desc={`数据截至 ${meta?.data_through ?? '—'}`} />
      <nav className="links">
        <Link className="linkrow" to="/margin">
          <span>两融</span>
          <span className="tag">circ-1000</span>
        </Link>
        <Link className="linkrow" to="/factors">
          <span>核心因子</span>
          <span className="tag">IC / 四态</span>
        </Link>
        <Link className="linkrow" to="/about">
          <span>关于 / 口径 / 数据缺口</span>
          <span className="tag">信息</span>
        </Link>
      </nav>
    </>
  )
}
