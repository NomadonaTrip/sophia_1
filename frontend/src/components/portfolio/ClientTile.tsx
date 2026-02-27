import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ClientData {
  id: number
  name: string
  status: 'cruising' | 'calibrating' | 'attention'
  postCount: number
  engagementRate: number
  trend: 'up' | 'down' | 'flat'
  voiceMatchPct: number
  sparkline: number[] // 6 values for mini bar chart
}

interface ClientTileProps {
  client: ClientData
  isSelected?: boolean
  onClick: (clientId: number) => void
}

const STATUS_BORDER: Record<string, string> = {
  cruising: 'border-l-sage-500',
  calibrating: 'border-l-amber-500',
  attention: 'border-l-coral-500',
}

const STATUS_LABEL_COLOR: Record<string, string> = {
  cruising: 'text-sage-400',
  calibrating: 'text-amber-400',
  attention: 'text-coral-400',
}

const SPARKLINE_COLOR: Record<string, string> = {
  cruising: 'bg-sage-500',
  calibrating: 'bg-amber-500',
  attention: 'bg-coral-500',
}

function TrendIcon({ trend }: { trend: 'up' | 'down' | 'flat' }) {
  switch (trend) {
    case 'up':
      return <TrendingUp className="h-3 w-3 text-sage-400" />
    case 'down':
      return <TrendingDown className="h-3 w-3 text-coral-400" />
    case 'flat':
      return <Minus className="h-3 w-3 text-text-muted" />
  }
}

function Sparkline({
  values,
  status,
}: {
  values: number[]
  status: string
}) {
  const max = Math.max(...values, 1)

  return (
    <div
      className="flex items-end gap-[2px] h-4"
      aria-label={`Engagement trend: ${status}`}
    >
      {values.map((v, i) => (
        <div
          key={i}
          className={cn('w-[3px] rounded-t-sm', SPARKLINE_COLOR[status])}
          style={{
            height: `${Math.max((v / max) * 100, 6)}%`,
            minHeight: '1px',
          }}
        />
      ))}
    </div>
  )
}

export function ClientTile({ client, isSelected = false, onClick }: ClientTileProps) {
  return (
    <button
      type="button"
      role="button"
      aria-label={`${client.name}, ${client.status}, ${client.engagementRate}% engagement`}
      onClick={() => onClick(client.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onClick(client.id)
      }}
      className={cn(
        'w-full text-left rounded-[14px] border bg-midnight-800 p-3 transition-all cursor-pointer border-l-[3px]',
        STATUS_BORDER[client.status],
        isSelected
          ? 'border-sage-500 ring-1 ring-sage-500/30 shadow-[0_0_12px_rgba(74,124,89,0.15)]'
          : 'border-midnight-700 hover:border-midnight-600 hover:shadow-md',
      )}
    >
      {/* Client name + post count badge */}
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-sm font-medium text-text-primary truncate">
          {client.name}
        </span>
        <span className="flex-none rounded-full bg-midnight-700 px-1.5 py-0.5 text-[10px] tabular-nums text-text-muted">
          {client.postCount}
        </span>
      </div>

      {/* Metrics row: engagement, sparkline, trend */}
      <div className="flex items-center gap-2">
        <span className={cn('text-xs tabular-nums font-medium', STATUS_LABEL_COLOR[client.status])}>
          {client.engagementRate}%
        </span>
        <Sparkline values={client.sparkline} status={client.status} />
        <TrendIcon trend={client.trend} />
      </div>

      {/* Voice match */}
      <div className="mt-1.5">
        <span className="text-[10px] text-text-muted">
          Voice {client.voiceMatchPct}%
        </span>
      </div>
    </button>
  )
}

export function ClientTileSkeleton() {
  return (
    <div className="rounded-[14px] border border-midnight-700 bg-midnight-800 p-3 border-l-[3px] border-l-sage-600">
      <div className="flex items-center justify-between mb-1.5">
        <div className="skeleton-sage h-4 w-24 rounded" />
        <div className="skeleton-sage h-4 w-6 rounded-full" />
      </div>
      <div className="flex items-center gap-2">
        <div className="skeleton-sage h-3 w-10 rounded" />
        <div className="skeleton-sage h-4 w-8 rounded" />
        <div className="skeleton-sage h-3 w-3 rounded" />
      </div>
      <div className="mt-1.5">
        <div className="skeleton-sage h-2.5 w-14 rounded" />
      </div>
    </div>
  )
}
