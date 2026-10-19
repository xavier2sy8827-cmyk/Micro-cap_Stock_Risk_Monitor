import { useEffect, useState } from 'react'

type Tab = {
  key: string
  label: string
  hint: string
  items: string[]
}

const TABS: Tab[] = [
  {
    key: 'overview',
    label: '总览',
    hint: '信号灯墙',
    items: ['微盘400 宽度分位', '估值价差 / 截面相关 / 多空波动比', 'qs_share', '两融池占比', '5 因子四态计数'],
  },
  {
    key: 'crowding',
    label: '拥挤度',
    hint: '宽度 / 三维度 / qs',
    items: ['微盘400 扩散指数 + 分位', 'pb_spread', 'corr60_wp400', 'ls_vol_ratio', 'qs_share'],
  },
  {
    key: 'alla',
    label: '全A',
    hint: '结构',
    items: ['申万一级行业扩散热力', '前 5% / 10% 成交额集中度', '五层成交额占比 + 750 日分位', '各层收益 MA5'],
  },
  {
    key: 'layers',
    label: '内部',
    hint: '10 层',
    items: ['L1–L10 扩散分位', 'L1–L10 收益 MA5', '哪一层在赚钱'],
  },
  {
    key: 'factors',
    label: '因子',
    hint: '四态',
    items: ['F1 SIZE / F2 DIV / F3 AMPL', 'F4 INTRA_REV / F5 RESID_REV', 'IC / 多空净值 / 四态', '预警事件与尾部不可判'],
  },
  {
    key: 'more',
    label: '更多',
    hint: '两融 / 关于',
    items: ['两融池占比（circ-1000，T-1）', 'wp400 观察值', '口径与数据来源', '缺口与降级记录'],
  },
]

type Theme = 'light' | 'dark'

function readTheme(): Theme | null {
  try {
    const v = localStorage.getItem('wp-theme')
    return v === 'light' || v === 'dark' ? v : null
  } catch {
    return null
  }
}

export default function App() {
  const [tab, setTab] = useState<string>('overview')
  const [theme, setTheme] = useState<Theme | null>(() => readTheme())

  useEffect(() => {
    const root = document.documentElement
    if (theme) root.setAttribute('data-theme', theme)
    else root.removeAttribute('data-theme')
    try {
      if (theme) localStorage.setItem('wp-theme', theme)
      else localStorage.removeItem('wp-theme')
    } catch {
      /* ignore */
    }
  }, [theme])

  const active = TABS.find((t) => t.key === tab) ?? TABS[0]

  return (
    <div className="app">
      <header className="head">
        <h1>微盘风险与监控</h1>
        <span className="meta">M0 · Pages 验证</span>
        <span className="spacer" />
        <button
          className="linkbtn"
          type="button"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          title="切换浅色 / 深色"
        >
          主题
        </button>
      </header>

      <div className="banner">
        数据管线尚未接入：本页只验证 GitHub Pages、移动端布局与主题。指标将在 M2 起接入。
      </div>

      <section className="kpi" aria-label="关键指标占位">
        <div className="cell">
          <div className="lab">宽度分位</div>
          <div className="val">—</div>
          <div className="sub">待接入</div>
        </div>
        <div className="cell">
          <div className="lab">估值价差</div>
          <div className="val">—</div>
          <div className="sub">待接入</div>
        </div>
        <div className="cell">
          <div className="lab">截面相关</div>
          <div className="val">—</div>
          <div className="sub">待接入</div>
        </div>
        <div className="cell">
          <div className="lab">多空波动比</div>
          <div className="val">—</div>
          <div className="sub">待接入</div>
        </div>
      </section>

      <nav className="tabs" role="tablist" aria-label="监控页面">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={t.key === active.key}
            className={t.key === active.key ? 'tab on' : 'tab'}
            type="button"
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <section className="panel" role="tabpanel">
        <div className="panel-head">
          <strong>{active.label}</strong>
          <span>{active.hint}</span>
        </div>
        <ul className="plan">
          {active.items.map((x) => (
            <li key={x}>
              <span>{x}</span>
              <span className="tag">待接入</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="note">
        <h2>部署自检</h2>
        <ul>
          <li>仓库：xavier2sy8827-cmyk/Micro-cap_Stock_Risk_Monitor</li>
          <li>站点：/Micro-cap_Stock_Risk_Monitor/（HashRouter）</li>
          <li>数据源：Tushare Pro（M1 接入）</li>
          <li>一期范围：纯监控，不含选股 / 持仓 / 盘中刷新</li>
        </ul>
      </section>

      <footer className="foot">
        <span>数据源 Tushare · 更新于 —</span>
        <span>构建 M0</span>
      </footer>
    </div>
  )
}
