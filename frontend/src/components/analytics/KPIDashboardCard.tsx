/**
 * Compact KPI display card for chat stream analytics.
 *
 * Shows a single KPI value with optional change indicator and status color.
 * Algorithm-independent metrics get a subtle sage border-left highlight.
 * Grid-friendly: works in 2-col, 3-col, or 4-col grid layouts.
 */

import { cn } from '@/lib/utils'

interface KPIDashboardCardProps {
  label: string
  value: string | number
  change?: number
  changeLabel?: string
  status?: 'sage' | 'amber' | 'coral'
  isAlgoIndependent?: boolean
}

const STATUS_COLORS = {
  sage: {
    dot: 'bg-[#4a7c59]',
    border: 'border-l-[#4a7c59]',
  },
  amber: {
    dot: 'bg-[#d97706]',
    border: 'border-l-[#d97706]',
  },
  coral: {
    dot: 'bg-[#ef4444]',
    border: 'border-l-[#ef4444]',
  },
} as const

export function KPIDashboardCard({
  label,
  value,
  change,
  changeLabel = 'vs last week',
  status,
  isAlgoIndependent = false,
}: KPIDashboardCardProps) {
  const statusConfig = status ? STATUS_COLORS[status] : null
  const displayValue =
    typeof value === 'number'
      ? value >= 1000
        ? `${(value / 1000).toFixed(1)}k`
        : value % 1 !== 0
          ? value.toFixed(2)
          : String(value)
      : value

  return (
    <div
      className={cn(
        'rounded-xl border border-midnight-700 bg-midnight-800 p-3',
        isAlgoIndependent && 'border-l-[3px] border-l-[#4a7c59]',
        statusConfig && !isAlgoIndependent && `border-l-[3px] ${statusConfig.border}`,
      )}
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-wide text-slate-400">
            {label}
          </p>
          <p className="mt-1 text-2xl font-bold text-white">{displayValue}</p>
        </div>

        {statusConfig && (
          <span
            className={cn('mt-1 h-2 w-2 flex-shrink-0 rounded-full', statusConfig.dot)}
          />
        )}
      </div>

      {change !== undefined && (
        <div className="mt-1.5 flex items-center gap-1 text-xs">
          {change > 0 ? (
            <span className="text-[#4a7c59]">
              {'\u2191'} {Math.abs(change).toFixed(1)}%
            </span>
          ) : change < 0 ? (
            <span className="text-[#ef4444]">
              {'\u2193'} {Math.abs(change).toFixed(1)}%
            </span>
          ) : (
            <span className="text-slate-400">-- 0%</span>
          )}
          <span className="text-slate-500">{changeLabel}</span>
        </div>
      )}
    </div>
  )
}
