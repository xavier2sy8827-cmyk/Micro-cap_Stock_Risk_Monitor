import { useEffect, useState } from 'react'

const BASE = import.meta.env.BASE_URL.endsWith('/') ? import.meta.env.BASE_URL : `${import.meta.env.BASE_URL}/`

export function dataUrl(name: string): string {
  return `${BASE}data/${name}`
}

interface State<T> {
  data: T | null
  error: string | null
  loading: boolean
}

export function useJson<T>(name: string): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })
  useEffect(() => {
    let alive = true
    setState({ data: null, error: null, loading: true })
    fetch(dataUrl(name), { cache: 'no-cache' })
      .then((r) => {
        if (!r.ok) throw new Error(`${name} HTTP ${r.status}`)
        return r.json() as Promise<T>
      })
      .then((d) => {
        if (alive) setState({ data: d, error: null, loading: false })
      })
      .catch((e: unknown) => {
        if (alive) setState({ data: null, error: String(e), loading: false })
      })
    return () => {
      alive = false
    }
  }, [name])
  return state
}
