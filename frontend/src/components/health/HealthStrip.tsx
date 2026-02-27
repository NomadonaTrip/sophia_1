import { Circle, Check } from 'lucide-react'
import { cn } from '@/lib/utils'

interface HealthStripProps {
  cruising: number
  calibrating: number
  attention: number
  postsRemaining: number
  isLoading?: boolean
}

function HealthStripSkeleton() {
  return (
    <div
      className="flex items-center gap-6 px-4 py-2 bg-midnight-800/80 backdrop-blur-sm border-b border-midnight-700"
      role="status"
      aria-label="Loading status"
    >
      <div className="skeleton-sage h-4 w-24 rounded" />
      <div className="skeleton-sage h-4 w-24 rounded" />
      <div className="skeleton-sage h-4 w-24 rounded" />
    </div>
  )
}

export function HealthStrip({
  cruising,
  calibrating,
  attention,
  postsRemaining,
  isLoading = false,
}: HealthStripProps) {
  if (isLoading) {
    return <HealthStripSkeleton />
  }

  const isQueueClear = cruising === 0 && calibrating === 0 && attention === 0

  return (
    <div
      className="flex items-center gap-4 sm:gap-6 px-4 py-2 bg-midnight-800/80 backdrop-blur-sm border-b border-midnight-700"
      role="status"
      aria-live="polite"
    >
      {isQueueClear ? (
        <div className="flex items-center gap-1.5 text-sage-300 text-xs">
          <Check className="h-3.5 w-3.5" />
          <span>Queue clear</span>
        </div>
      ) : (
        <>
          <StatusCount
            count={cruising}
            label="Cruising"
            colorClass="text-sage-400"
            dotColorClass="fill-sage-400 text-sage-400"
          />
          <StatusCount
            count={calibrating}
            label="Calibrating"
            colorClass="text-amber-400"
            dotColorClass="fill-amber-400 text-amber-400"
          />
          <StatusCount
            count={attention}
            label="Attention"
            colorClass="text-coral-400"
            dotColorClass="fill-coral-400 text-coral-400"
          />
        </>
      )}

      <div className="ml-auto text-xs text-text-muted">
        <span className="tabular-nums">{postsRemaining}</span> posts remaining
      </div>
    </div>
  )
}

function StatusCount({
  count,
  label,
  colorClass,
  dotColorClass,
}: {
  count: number
  label: string
  colorClass: string
  dotColorClass: string
}) {
  return (
    <div className={cn('flex items-center gap-1.5 text-xs', colorClass)}>
      <Circle className={cn('h-2.5 w-2.5', dotColorClass)} />
      <span className="tabular-nums">{count}</span>
      <span className="hidden sm:inline text-text-muted">{label}</span>
    </div>
  )
}
