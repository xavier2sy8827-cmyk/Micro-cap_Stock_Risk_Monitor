import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { useJson } from './lib/data'
import type { Meta } from './lib/types'
import { MetaProvider } from './meta'
import AboutPage from './pages/About'
import AllAPage from './pages/AllA'
import CrowdingPage from './pages/Crowding'
import FactorsPage from './pages/Factors'
import LayersPage from './pages/Layers'
import MarginPage from './pages/Margin'
import MorePage from './pages/More'
import Overview from './pages/Overview'

type Theme = 'light' | 'dark'

function readTheme(): Theme | null {
  try {
    const v = localStorage.getItem('wp-theme')
    return v === 'light' || v === 'dark' ? v : null
  } catch {
    return null
  }
}

const NAV = [
  { to: '/', label: '总览', end: true },
  { to: '/crowding', label: '拥挤度' },
  { to: '/alla', label: '全A' },
  { to: '/layers', label: '内部' },
  { to: '/more', label: '更多' },
]

export default function App() {
  const [theme, setTheme] = useState<Theme | null>(() => readTheme())
  const { data: meta, error, loading } = useJson<Meta>('meta.json')

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

  return (
    <MetaProvider value={meta}>
      <div className="app">
        <header className="head">
          <h1>微盘风险与监控</h1>
          <span className="meta">
            {loading ? '数据加载中' : meta ? `数据 ${meta.data_through}` : '数据未就绪'}
          </span>
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

        {error ? <div className="banner">元数据加载失败：{error}</div> : null}
        {meta && meta.margin_through && meta.margin_through !== meta.data_through ? (
          <div className="subtle">两融数据截至 {meta.margin_through}（T-1 发布）</div>
        ) : null}

        <main className="main">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/crowding" element={<CrowdingPage />} />
            <Route path="/alla" element={<AllAPage />} />
            <Route path="/layers" element={<LayersPage />} />
            <Route path="/margin" element={<MarginPage />} />
            <Route path="/factors" element={<FactorsPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/more" element={<MorePage />} />
            <Route path="*" element={<Overview />} />
          </Routes>
        </main>

        <footer className="foot">
          <span>数据源 Tushare · {meta?.generated_at ?? '—'}</span>
          <span>{meta?.days ? `${meta.days} 交易日` : '—'}</span>
        </footer>

        <nav className="nav" aria-label="主导航">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? 'on' : '')}>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </MetaProvider>
  )
}
