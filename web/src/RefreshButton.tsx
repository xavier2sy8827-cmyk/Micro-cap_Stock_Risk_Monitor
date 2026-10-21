import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getRefreshStatus,
  readRefreshKey,
  refreshEnabled,
  saveRefreshKey,
  triggerRefresh,
  waitForPages,
  type RefreshStatus,
} from './lib/refresh'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

function errorText(status: number, body: Record<string, unknown>): string {
  if (status === 401) return '刷新口令错误'
  if (status === 403) return '来源不被允许'
  if (status === 429) {
    const s = Number(body.retry_after ?? 600)
    return `触发太频繁，请 ${Math.max(1, Math.ceil(s / 60))} 分钟后再试`
  }
  if (status === 409) return '已有更新任务在跑'
  if (status === 502) return 'GitHub 授权失败，请检查 Worker secret'
  return `触发失败（HTTP ${status}）`
}

export function RefreshButton() {
  const [busy, setBusy] = useState(false)
  const [text, setText] = useState('更新数据')
  const [detail, setDetail] = useState('')
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const finish = useCallback((msg: string) => {
    setText(msg)
    setBusy(false)
    window.setTimeout(() => {
      if (alive.current) setText('更新数据')
    }, 4000)
  }, [])

  const run = useCallback(async () => {
    if (busy) return
    setBusy(true)
    setText('触发中…')
    setDetail('')

    let before: RefreshStatus | null = null
    try {
      before = await getRefreshStatus()
    } catch {
      before = null
    }

    const key = readRefreshKey()
    let res = await triggerRefresh(key)
    if (res.status === 401 && res.body.error === 'key') {
      const input = window.prompt('请输入刷新口令')
      if (!input) {
        finish('已取消')
        return
      }
      saveRefreshKey(input)
      res = await triggerRefresh(input)
    }

    const attachedRun = res.status === 409
    if (res.status >= 400 && !attachedRun) {
      finish(errorText(res.status, res.body))
      setDetail(String(res.body.error ?? ''))
      return
    }

    const dispatchedAt = String(res.body.dispatched_at ?? new Date().toISOString())
    const dispatchedMs = Date.parse(dispatchedAt)
    const beforeDate = before?.last_data_through ?? ''
    const graceUntil = Date.now() + 60_000
    let sawActive = attachedRun
    const deadline = Date.now() + 20 * 60 * 1000

    setText('更新中…')
    while (Date.now() < deadline && alive.current) {
      await sleep(document.hidden ? 15000 : 5000)
      if (!alive.current) return
      let st: RefreshStatus
      try {
        st = await getRefreshStatus()
      } catch {
        continue
      }

      const isNewRun =
        !!st.run?.created_at && Date.parse(st.run.created_at) >= dispatchedMs - 120_000
      if (st.active) {
        sawActive = true
        continue
      }
      if (attachedRun && !isNewRun) {
        if (!sawActive || st.run?.status !== 'completed') continue
        if (st.last_data_through && st.last_data_through > beforeDate) {
          setText(`已更新 ${st.last_data_through}`)
          await waitForPages(st.last_data_through, setText)
          return
        }
        finish('已是最新')
        return
      }
      if (!isNewRun) {
        if (Date.now() < graceUntil) continue
        continue
      }
      if (st.run?.conclusion === 'failure' || st.run?.conclusion === 'cancelled') {
        setDetail(st.run.html_url)
        finish('更新失败，查看 Actions')
        return
      }
      if (st.last_data_through && st.last_data_through > beforeDate) {
        setText(`已更新 ${st.last_data_through}`)
        await waitForPages(st.last_data_through, setText)
        return
      }
      if (st.run?.status === 'completed') {
        finish('已是最新')
        return
      }
    }
    finish('更新超时，查看 Actions')
  }, [busy, finish])

  if (!refreshEnabled) return null

  return (
    <button
      className="linkbtn"
      type="button"
      disabled={busy}
      title={detail || '触发 GitHub Actions 更新数据'}
      onClick={run}
    >
      {text}
    </button>
  )
}
