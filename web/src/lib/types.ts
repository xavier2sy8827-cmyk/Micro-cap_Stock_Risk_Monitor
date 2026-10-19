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
  layers: { key: string; breadth: Num[]; pct: Num[]; ret_ma5: Num[]; n_valid: Num[] }[]
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
