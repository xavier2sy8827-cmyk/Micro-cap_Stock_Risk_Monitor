export type Num = number | null

export interface PctSeries {
  v: Num[]
  pct?: Num[]
  pct_exp?: Num[]
}

export interface Signal {
  key: string
  label: string
  value: Num
  pct: Num
  z?: Num
  unit: string
  level: 'normal' | 'warn' | 'danger' | 'hot' | 'cold'
  asof: string | null
}

export interface Meta {
  schema_version: number
  generated_at: string
  generated_tz?: string
  data_through: string
  margin_through?: string | null
  factor_ic_through?: string | null
  industry_version: string
  warnings: string[]
  days?: number
  pipeline_version?: string
}

export interface Overview {
  signals: Signal[]
  spark: { dates: string[]; series: { key: string; values: Num[] }[] }
}

export interface Crowding {
  dates: string[]
  breadth10: PctSeries
  wp400_index: Num[]
  pb_spread: PctSeries
  corr60_wp400: PctSeries
  ls_vol_ratio: PctSeries
  qs: PctSeries & { subset_n: Num[]; valid_n: Num[]; abs: Num[] }
}

export interface AllA {
  dates: string[]
  industries: { names: string[]; matrix: Num[][] }
  s_width: Num[]
  s_width_pct: Num[]
  s_width_pctile: Num[]
  n_industries: Num[]
  top5: { v: Num[]; pct: Num[] }
  top10: { v: Num[]; pct: Num[] }
  five_layer: {
    names: string[]
    money: Record<string, Num[]>
    share: Record<string, Num[]>
    share_pct: Record<string, Num[]>
    ret_ma5: Record<string, Num[]>
  }
}

export interface Layers {
  dates: string[]
  layers: {
    key: string
    breadth: Num[]
    pct: Num[]
    ret_1d: Num[]
    ret_ma5: Num[]
    ret_ma10: Num[]
    ret_ma20: Num[]
    n_valid: Num[]
  }[]
}

export interface Margin {
  dates: string[]
  through: string | null
  ratio: Num[]
  ratio_z: Num[]
  buy_ratio: Num[]
  n: Num[]
  wp400_ratio: Num[]
  wp400_n: Num[]
}

export interface FactorStates {
  state: Num[]
  L: Num[]
  D: Num[]
  R: Num[]
  F: Num[]
  judge_nan: Num[]
}

export interface FactorEvent {
  factor: string
  event_date: string
  confirm_date?: string | null
  end_date?: string | null
  confirmed?: boolean | string
  depth?: number | null
  sigma_mult?: number | null
  days?: number | null
  reason?: string | null
}

export interface Factors {
  dates: string[]
  factors: string[]
  names: Record<string, string>
  states: Record<string, FactorStates>
  ic: Record<string, Num[]>
  ic_mean_252: Record<string, Num[]>
  icir_252: Record<string, Num[]>
  ls_nav: Record<string, Num[]>
  events: FactorEvent[]
  tail_gap: number
  updated_through?: string | null
}
