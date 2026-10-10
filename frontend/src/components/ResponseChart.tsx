import { useMemo } from 'react'
import {
  CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceDot, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { Sample } from '../api'
import { num, yMax } from '../format'

export interface Series {
  id: string
  label: string
  color: string
  samples: Sample[]
  dashed?: boolean
  peak?: { frequency: number; magnitude: number } | null
}

interface Props {
  series: Series[]
  limit: number
  unit: string
  rangeMin: number
  rangeMax: number
  zoomToRange: boolean
  height?: number
}

type Row = { f: number } & Record<string, number | undefined>

export function ResponseChart({ series, limit, unit, rangeMin, rangeMax, zoomToRange, height = 380 }: Props) {
  const { rows, ymax, xmax, yTicks } = useMemo(() => {
    const byF = new Map<number, Row>()
    for (const s of series)
      for (const p of s.samples) {
        const row = byF.get(p.frequency) ?? ({ f: p.frequency } as Row)
        row[s.id] = p.magnitude
        byF.set(p.frequency, row)
      }
    const all = [...byF.values()].sort((a, b) => a.f - b.f)
    const visible = zoomToRange ? all.filter((r) => r.f <= rangeMax * 1.1) : all
    const peaks = series.flatMap((s) => s.samples.filter((p) => !zoomToRange || p.frequency <= rangeMax * 1.1).map((p) => p.magnitude))
    const xm = zoomToRange ? Math.ceil(rangeMax * 1.1) : Math.max(...all.map((r) => r.f))
    const ym = yMax(peaks, limit)
    const step = ym > 40 ? 10 : 5
    return { rows: visible, ymax: ym, xmax: xm, yTicks: Array.from({ length: ym / step + 1 }, (_, i) => i * step) }
  }, [series, limit, rangeMax, zoomToRange])

  return (
    <div className="chart" role="img" aria-label={`Frequency response chart, magnitude in ${unit} versus frequency in Hz, with the ${limit} ${unit} limit marked`}>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ top: 18, right: 24, bottom: 28, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <ReferenceArea x1={rangeMin} x2={rangeMax} fill="var(--range)" fillOpacity={1} ifOverflow="visible"
            label={{ value: `Assessed range ${rangeMin}–${rangeMax} Hz`, position: 'insideTopLeft', fill: 'var(--muted)', fontSize: 12 }} />
          <XAxis dataKey="f" type="number" domain={[0, xmax]} allowDataOverflow tick={{ fill: 'var(--muted)', fontSize: 12 }}
            label={{ value: 'Frequency [Hz]', position: 'insideBottom', offset: -16, fill: 'var(--muted)', fontSize: 12 }} />
          <YAxis domain={[0, ymax]} ticks={yTicks} tick={{ fill: 'var(--muted)', fontSize: 12 }} width={52}
            label={{ value: `Magnitude [${unit}]`, angle: -90, position: 'insideLeft', offset: 4, fill: 'var(--muted)', fontSize: 12, style: { textAnchor: 'middle' } }} />
          <ReferenceLine y={limit} stroke="var(--fail)" strokeDasharray="6 4" strokeWidth={1.5}
            label={{ value: `Limit ${limit} ${unit}`, position: 'insideBottomRight', fill: 'var(--fail)', fontSize: 12, fontWeight: 600 }} />
          <ReferenceLine x={rangeMax} stroke="var(--muted)" strokeDasharray="2 3" />
          <Tooltip content={<ChartTooltip series={series} unit={unit} />} />
          {series.map((s) => (
            <Line key={s.id} dataKey={s.id} name={s.label} stroke={s.color} strokeWidth={2.25} connectNulls
              strokeDasharray={s.dashed ? '5 4' : undefined} dot={{ r: 3, fill: s.color, strokeWidth: 0 }}
              activeDot={{ r: 5 }} isAnimationActive={false} />
          ))}
          {series.map((s, si) =>
            s.peak && (!zoomToRange || s.peak.frequency <= rangeMax * 1.1) ? (
              <ReferenceDot key={`pk-${s.id}`} x={s.peak.frequency} y={s.peak.magnitude} r={7} fill="none" stroke={s.color} strokeWidth={2.5} ifOverflow="visible"
                label={{ value: `${num(s.peak.magnitude)} ${unit} @ ${num(s.peak.frequency)} Hz`, position: si === 0 ? 'top' : 'right', fill: s.color, fontSize: 12, fontWeight: 600 }} />
            ) : null,
          )}
        </ComposedChart>
      </ResponsiveContainer>
      {series.length > 1 && (
        <ul className="legend">
          {series.map((s) => (
            <li key={s.id}><span className="swatch" style={{ borderTopColor: s.color, borderTopStyle: s.dashed ? 'dashed' : 'solid' }} />{s.label}</li>
          ))}
          <li><span className="swatch limit" />Limit</li>
          <li><span className="swatch ring" />Peak in assessed range</li>
        </ul>
      )}
    </div>
  )
}

function ChartTooltip({ active, payload, label, series, unit }: { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: number; series: Series[]; unit: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="tooltip">
      <div className="tt-head">{num(label)} Hz</div>
      {payload.map((p) => {
        const s = series.find((x) => x.id === p.dataKey)
        return s ? (
          <div key={p.dataKey} className="tt-row">
            <span className="swatch" style={{ borderTopColor: s.color }} /> {s.label}: <b>{num(p.value, 2)} {unit}</b>
          </div>
        ) : null
      })}
    </div>
  )
}

export function DeltaChart({ points, unit, rangeMax, zoomToRange }: { points: { frequency: number; delta: number }[]; unit: string; rangeMax: number; zoomToRange: boolean }) {
  const rows = zoomToRange ? points.filter((p) => p.frequency <= rangeMax * 1.1) : points
  const m = Math.max(1, ...rows.map((r) => Math.abs(r.delta)))
  const lim = Math.ceil(m)
  return (
    <div className="chart" role="img" aria-label={`Difference between revisions in ${unit} versus frequency`}>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={rows} margin={{ top: 10, right: 24, bottom: 28, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <ReferenceArea x1={0} x2={rangeMax} fill="var(--range)" fillOpacity={1} ifOverflow="visible" />
          <XAxis dataKey="frequency" type="number" domain={[0, zoomToRange ? Math.ceil(rangeMax * 1.1) : 'dataMax']} allowDataOverflow tick={{ fill: 'var(--muted)', fontSize: 12 }}
            label={{ value: 'Frequency [Hz]', position: 'insideBottom', offset: -16, fill: 'var(--muted)', fontSize: 12 }} />
          <YAxis domain={[-lim, lim]} ticks={[-lim, -lim / 2, 0, lim / 2, lim]} tick={{ fill: 'var(--muted)', fontSize: 12 }} width={52}
            label={{ value: `Δ [${unit}]`, angle: -90, position: 'insideLeft', offset: 4, fill: 'var(--muted)', fontSize: 12 }} />
          <ReferenceLine y={0} stroke="var(--muted)" />
          <Tooltip formatter={(v) => [`${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(2)} ${unit}`, 'Δ (target − base)']} labelFormatter={(l) => `${num(Number(l))} Hz`} />
          <Line dataKey="delta" stroke="var(--accent)" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
