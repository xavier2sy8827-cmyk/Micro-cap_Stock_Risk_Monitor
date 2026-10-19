import { createContext, useContext } from 'react'
import type { Meta } from './lib/types'

const MetaCtx = createContext<Meta | null>(null)

export const MetaProvider = MetaCtx.Provider

export function useMeta(): Meta | null {
  return useContext(MetaCtx)
}

export function asofText(meta: Meta | null): string {
  return meta?.data_through ?? '—'
}
