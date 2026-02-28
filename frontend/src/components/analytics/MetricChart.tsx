/**
 * Universal Recharts wrapper for line, bar, radar, and composed charts.
 *
 * Renders analytics inline in the chat stream at full width.
 * Midnight Sage design system: bg-midnight-800, border-midnight-700, sage accents.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ComposedChart,
} from 'recharts'
import type { CSSProperties } from 'react'
import { cn } from '@/lib/utils'

interface MetricChartProps {
  type: 'line' | 'bar' | 'radar' | 'composed'
  data: Array<Record<string, unknown>>
  dataKey: string
  xAxisKey?: string
  secondaryDataKey?: string
  title?: string
  height?: number
  showGrid?: boolean
}

const SAGE = '#4a7c59'
const AMBER = '#d97706'

const tooltipStyle: CSSProperties = {
  backgroundColor: '#0f1419',
  border: '1px solid #1e2a35',
  borderRadius: '8px',
  color: '#ffffff',
  fontSize: '12px',
}

function LineChartContent({
  data,
  dataKey,
  xAxisKey,
  showGrid,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  xAxisKey: string
  showGrid: boolean
}) {
  return (
    <LineChart data={data}>
      {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#1e2a35" />}
      <XAxis
        dataKey={xAxisKey}
        tick={{ fill: '#94a3b8', fontSize: 11 }}
        stroke="#1e2a35"
      />
      <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} stroke="#1e2a35" />
      <Tooltip contentStyle={tooltipStyle} />
      <Line
        type="monotone"
        dataKey={dataKey}
        stroke={SAGE}
        strokeWidth={2}
        dot={{ fill: SAGE, r: 3 }}
        activeDot={{ r: 5 }}
      />
    </LineChart>
  )
}

function BarChartContent({
  data,
  dataKey,
  xAxisKey,
  showGrid,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  xAxisKey: string
  showGrid: boolean
}) {
  return (
    <BarChart data={data}>
      {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#1e2a35" />}
      <XAxis
        dataKey={xAxisKey}
        tick={{ fill: '#94a3b8', fontSize: 11 }}
        stroke="#1e2a35"
      />
      <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} stroke="#1e2a35" />
      <Tooltip contentStyle={tooltipStyle} />
      <Bar dataKey={dataKey} fill={SAGE} radius={[4, 4, 0, 0]} />
    </BarChart>
  )
}

function RadarChartContent({
  data,
  dataKey,
  xAxisKey,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  xAxisKey: string
}) {
  return (
    <RadarChart data={data} cx="50%" cy="50%" outerRadius="80%">
      <PolarGrid stroke="#1e2a35" />
      <PolarAngleAxis
        dataKey={xAxisKey}
        tick={{ fill: '#94a3b8', fontSize: 11 }}
      />
      <PolarRadiusAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
      <Tooltip contentStyle={tooltipStyle} />
      <Radar
        dataKey={dataKey}
        stroke={SAGE}
        fill={SAGE}
        fillOpacity={0.2}
      />
    </RadarChart>
  )
}

function ComposedChartContent({
  data,
  dataKey,
  secondaryDataKey,
  xAxisKey,
  showGrid,
}: {
  data: Array<Record<string, unknown>>
  dataKey: string
  secondaryDataKey?: string
  xAxisKey: string
  showGrid: boolean
}) {
  return (
    <ComposedChart data={data}>
      {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="#1e2a35" />}
      <XAxis
        dataKey={xAxisKey}
        tick={{ fill: '#94a3b8', fontSize: 11 }}
        stroke="#1e2a35"
      />
      <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} stroke="#1e2a35" />
      <Tooltip contentStyle={tooltipStyle} />
      <Bar dataKey={dataKey} fill={SAGE} radius={[4, 4, 0, 0]} />
      {secondaryDataKey && (
        <Line
          type="monotone"
          dataKey={secondaryDataKey}
          stroke={AMBER}
          strokeWidth={2}
          dot={{ fill: AMBER, r: 3 }}
        />
      )}
    </ComposedChart>
  )
}

export function MetricChart({
  type,
  data,
  dataKey,
  xAxisKey = 'name',
  secondaryDataKey,
  title,
  height = 200,
  showGrid = true,
}: MetricChartProps) {
  return (
    <div
      className={cn(
        'w-full rounded-[14px] border border-midnight-700 bg-midnight-800 p-3',
      )}
    >
      {title && (
        <h4 className="mb-2 text-sm font-medium text-sage-300">{title}</h4>
      )}
      <ResponsiveContainer width="100%" height={height}>
        {type === 'line' ? (
          <LineChartContent
            data={data}
            dataKey={dataKey}
            xAxisKey={xAxisKey}
            showGrid={showGrid}
          />
        ) : type === 'bar' ? (
          <BarChartContent
            data={data}
            dataKey={dataKey}
            xAxisKey={xAxisKey}
            showGrid={showGrid}
          />
        ) : type === 'radar' ? (
          <RadarChartContent
            data={data}
            dataKey={dataKey}
            xAxisKey={xAxisKey}
          />
        ) : (
          <ComposedChartContent
            data={data}
            dataKey={dataKey}
            secondaryDataKey={secondaryDataKey}
            xAxisKey={xAxisKey}
            showGrid={showGrid}
          />
        )}
      </ResponsiveContainer>
    </div>
  )
}
