/**
 * Optimal posting time heatmap for chat stream analytics.
 *
 * Displays a 1x24 hour grid showing average engagement rate per posting hour.
 * Color intensity scales from midnight-800 (low) through sage shades (high).
 * Full chat width, Midnight Sage design system.
 */

import { cn } from '@/lib/utils'
import { useState } from 'react'

interface PostingHeatmapProps {
  /** Mapping of hour (0-23) to average engagement rate */
  data: Record<string, number>
  platform: string
}

/**
 * Map engagement rate to a background color class.
 * Low = midnight, medium = sage with low opacity, high = sage with full opacity.
 */
function getHeatColor(value: number, maxValue: number): string {
  if (maxValue === 0) return 'bg-midnight-800'
  const ratio = value / maxValue
  if (ratio < 0.2) return 'bg-midnight-800'
  if (ratio < 0.4) return 'bg-[#4a7c59]/20'
  if (ratio < 0.6) return 'bg-[#4a7c59]/40'
  if (ratio < 0.8) return 'bg-[#4a7c59]/60'
  return 'bg-[#4a7c59]'
}

function formatHour(hour: number): string {
  if (hour === 0) return '12a'
  if (hour === 12) return '12p'
  if (hour < 12) return `${hour}a`
  return `${hour - 12}p`
}

export function PostingHeatmap({ data, platform }: PostingHeatmapProps) {
  const [hoveredHour, setHoveredHour] = useState<number | null>(null)

  // Build 24-hour array
  const hours = Array.from({ length: 24 }, (_, i) => ({
    hour: i,
    value: data[String(i)] ?? 0,
  }))

  const maxValue = Math.max(...hours.map((h) => h.value), 0.001)

  // Find optimal hour
  const bestHour = hours.reduce(
    (best, h) => (h.value > best.value ? h : best),
    hours[0]!,
  )

  return (
    <div className="w-full rounded-[14px] border border-midnight-700 bg-midnight-800 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-medium text-sage-300">
          Best posting times ({platform})
        </h4>
        {bestHour.value > 0 && (
          <span className="text-xs text-slate-400">
            Peak: {formatHour(bestHour.hour)} (
            {(bestHour.value * 100).toFixed(1)}% ER)
          </span>
        )}
      </div>

      {/* Heatmap grid */}
      <div className="flex gap-0.5">
        {hours.map(({ hour, value }) => (
          <div
            key={hour}
            className="relative flex-1"
            onMouseEnter={() => setHoveredHour(hour)}
            onMouseLeave={() => setHoveredHour(null)}
          >
            <div
              className={cn(
                'h-8 rounded-sm transition-colors',
                getHeatColor(value, maxValue),
                hour === bestHour.hour && 'ring-1 ring-[#4a7c59]',
              )}
            />
            {/* Hour label (show every 3 hours to avoid crowding) */}
            {hour % 3 === 0 && (
              <span className="mt-0.5 block text-center text-[9px] text-slate-500">
                {formatHour(hour)}
              </span>
            )}

            {/* Tooltip on hover */}
            {hoveredHour === hour && (
              <div className="absolute -top-10 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded bg-midnight-900 border border-midnight-700 px-2 py-1 text-xs text-white shadow-lg">
                {formatHour(hour)}: {(value * 100).toFixed(2)}% ER
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-2 flex items-center justify-end gap-1 text-[9px] text-slate-500">
        <span>Low</span>
        <div className="flex gap-0.5">
          <span className="inline-block h-2 w-3 rounded-sm bg-midnight-800" />
          <span className="inline-block h-2 w-3 rounded-sm bg-[#4a7c59]/20" />
          <span className="inline-block h-2 w-3 rounded-sm bg-[#4a7c59]/40" />
          <span className="inline-block h-2 w-3 rounded-sm bg-[#4a7c59]/60" />
          <span className="inline-block h-2 w-3 rounded-sm bg-[#4a7c59]" />
        </div>
        <span>High</span>
      </div>
    </div>
  )
}
