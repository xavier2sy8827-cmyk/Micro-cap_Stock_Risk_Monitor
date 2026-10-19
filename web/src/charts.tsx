import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { HeatmapChart, LineChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsOption } from 'echarts'
import type { Num } from './lib/types'

echarts.use([
  LineChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  DataZoomComponent,
  LegendComponent,
  MarkLineComponent,
  VisualMapComponent,
  CanvasRenderer,
])

const AXIS = '#8a8a90'
const HAIR = 'rgba(128,128,128,.22)'

function useChart(option: EChartsOption, height: number) {
  const ref = useRef<HTMLDivElement | null>(null)
  const inst = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const chart = echarts.init(el)
    inst.current = chart
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(el)
    return () => {
      ro.disconnect()
      chart.dispose()
      inst.current = null
    }
  }, [])

  useEffect(() => {
    inst.current?.setOption(option, true)
  }, [option])

  return <div ref={ref} style={{ height }} />
}

export interface LineDef {
  label: string
  values: Num[]
  color: string
  dashed?: boolean
}

interface PanelProps {
  dates: string[]
  lines: LineDef[]
  height: number
  showX: boolean
  thresholds?: number[]
  yMin?: number
  yMax?: number
  showLegend?: boolean
}

function LinePanel({ dates, lines, height, showX, thresholds = [], yMin, yMax, showLegend = true }: PanelProps) {
  const series = lines.map((l, i) => ({
    name: l.label,
    type: 'line' as const,
    data: l.values,
    showSymbol: false,
    connectNulls: false,
    sampling: 'lttb' as const,
    lineStyle: { width: 1.4, color: l.color, type: l.dashed ? ('dashed' as const) : ('solid' as const) },
    itemStyle: { color: l.color },
    markLine:
      i === 0 && thresholds.length > 0
        ? {
            silent: true,
            symbol: 'none',
            label: { position: 'insideEndTop' as const, fontSize: 9, color: AXIS, formatter: '{c}' },
            lineStyle: { color: 'rgba(213,73,92,.45)', type: 'dashed' as const, width: 1 },
            data: thresholds.map((t) => ({ yAxis: t })),
          }
        : undefined,
  })) as unknown as EChartsOption['series']

  const option: EChartsOption = {
    animation: false,
    grid: { left: 40, right: 10, top: lines.length > 1 ? 24 : 6, bottom: showX ? 18 : 6 },
    legend:
      showLegend && lines.length > 1
        ? { top: 2, left: 40, itemWidth: 10, itemHeight: 6, textStyle: { fontSize: 9, color: AXIS } }
        : undefined,
    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'line' },
      textStyle: { fontSize: 11 },
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: HAIR } },
      axisTick: { show: false },
      axisLabel: {
        show: showX,
        color: AXIS,
        fontSize: 9,
        interval: Math.max(0, Math.floor(dates.length / 3)),
        formatter: (v: string) => v.slice(5),
      },
    },
    yAxis: {
      type: 'value',
      scale: yMin === undefined,
      min: yMin,
      max: yMax,
      axisLabel: { color: AXIS, fontSize: 9 },
      splitLine: { lineStyle: { color: HAIR } },
    },
    dataZoom: [{ type: 'inside', filterMode: 'none' }],
    series,
  }
  return useChart(option, height)
}

interface TimeSeriesProps {
  dates: string[]
  lines: LineDef[]
  pct?: Num[]
  pctExp?: Num[]
  thresholds?: number[]
  height?: number
}

export function TimeSeries({ dates, lines, pct, pctExp, thresholds = [], height = 230 }: TimeSeriesProps) {
  const hasPct = Array.isArray(pct) && pct.some((v) => v !== null)
  const pctLines: LineDef[] = []
  if (hasPct) {
    pctLines.push({ label: '滚动分位', values: pct as Num[], color: '#2b6cb0' })
    if (pctExp) pctLines.push({ label: '全样本分位', values: pctExp, color: '#805ad5', dashed: true })
  }

  return (
    <>
      <LinePanel dates={dates} lines={lines} height={hasPct ? Math.max(150, height - 100) : height} showX={!hasPct} />
      {hasPct ? (
        <LinePanel
          dates={dates}
          lines={pctLines}
          height={100}
          showX
          thresholds={thresholds}
          yMin={0}
          yMax={100}
          showLegend={false}
        />
      ) : null}
    </>
  )
}

interface HeatmapProps {
  names: string[]
  matrix: Num[][]
  dates: string[]
  height?: number
  max?: number
  colors?: string[]
}

export function Heatmap({
  names,
  matrix,
  dates,
  height = 420,
  max = 100,
  colors = ['#2f6fed', '#eef2f7', '#d5495c'],
}: HeatmapProps) {
  const data: [number, number, number][] = []
  for (let y = 0; y < names.length; y += 1) {
    const row = matrix[y] ?? []
    for (let x = 0; x < dates.length; x += 1) {
      const v = row[x]
      if (v !== null && Number.isFinite(v as number)) data.push([x, y, v as number])
    }
  }
  const option: EChartsOption = {
    animation: false,
    tooltip: { confine: true, textStyle: { fontSize: 11 } },
    grid: { left: 76, right: 10, top: 8, bottom: 42 },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: HAIR } },
      axisTick: { show: false },
      axisLabel: {
        color: AXIS,
        fontSize: 9,
        interval: Math.max(0, Math.floor(dates.length / 3)),
        formatter: (v: string) => v.slice(5),
      },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { lineStyle: { color: HAIR } },
      axisTick: { show: false },
      axisLabel: { color: AXIS, fontSize: 9 },
    },
    visualMap: {
      min: 0,
      max,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 2,
      itemWidth: 8,
      itemHeight: 50,
      textStyle: { fontSize: 9, color: AXIS },
      inRange: { color: colors },
    },
    series: [
      {
        type: 'heatmap',
        data,
        progressive: 5000,
        itemStyle: { borderWidth: 0.3, borderColor: 'rgba(128,128,128,.15)' },
      },
    ],
  }
  return useChart(option, height)
}

export function Sparkline({
  values,
  color = '#2f6fed',
  height = 28,
}: {
  values: Num[]
  color?: string
  height?: number
}) {
  const pts = values.filter((v): v is number => v !== null && Number.isFinite(v))
  if (pts.length < 2) return <div style={{ height }} />
  const min = Math.min(...pts)
  const max = Math.max(...pts)
  const span = max - min || 1
  const w = 100
  const h = height
  const step = w / (pts.length - 1)
  const points = pts
    .map((v, i) => `${(i * step).toFixed(2)},${(h - ((v - min) / span) * (h - 4) - 2).toFixed(2)}`)
    .join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
