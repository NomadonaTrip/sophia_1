/**
 * Morning brief portfolio grid with sage/amber/coral status tiles.
 *
 * Displays 20-client portfolio overview inline in the chat stream.
 * Coral clients pulse for attention, amber clients are elevated,
 * sage clients are cruising with no special treatment.
 */

import { cn } from '@/lib/utils'
import { useState } from 'react'

interface ClientTile {
  client_id: number
  client_name: string
  status_color: 'sage' | 'amber' | 'coral'
  engagement_rate: number
  follower_growth_pct: number
  anomaly_count: number
  top_anomaly?: string
}

interface PortfolioAnalyticsProps {
  clients: ClientTile[]
  summaryStats: {
    total_clients: number
    sage_count: number
    amber_count: number
    coral_count: number
  }
}

const STATUS_CONFIG = {
  sage: {
    borderColor: 'border-l-[#4a7c59]',
    label: 'cruising',
  },
  amber: {
    borderColor: 'border-l-[#d97706]',
    label: 'calibrating',
  },
  coral: {
    borderColor: 'border-l-[#ef4444]',
    label: 'attention',
  },
} as const

function ClientTileCard({ client }: { client: ClientTile }) {
  const [showDetails, setShowDetails] = useState(false)
  const config = STATUS_CONFIG[client.status_color]

  return (
    <div
      className={cn(
        'relative rounded-lg border border-midnight-700 bg-midnight-800 p-2.5 border-l-[4px] transition-colors',
        config.borderColor,
        client.status_color === 'amber' && 'shadow-sm',
      )}
      onMouseEnter={() => setShowDetails(true)}
      onMouseLeave={() => setShowDetails(false)}
    >
      {/* Pulsing attention dot for coral clients */}
      {client.status_color === 'coral' && (
        <span className="absolute right-2 top-2 flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#ef4444] opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-[#ef4444]" />
        </span>
      )}

      <p className="truncate text-sm font-medium text-white">
        {client.client_name}
      </p>
      <p className="mt-0.5 text-xs text-slate-400">
        ER: {(client.engagement_rate * 100).toFixed(1)}%
        {client.follower_growth_pct !== 0 && (
          <span
            className={cn(
              'ml-2',
              client.follower_growth_pct > 0
                ? 'text-[#4a7c59]'
                : 'text-[#ef4444]',
            )}
          >
            {client.follower_growth_pct > 0 ? '+' : ''}
            {client.follower_growth_pct.toFixed(1)}% growth
          </span>
        )}
      </p>

      {/* Anomaly details on hover */}
      {showDetails && client.anomaly_count > 0 && client.top_anomaly && (
        <div className="mt-1.5 rounded bg-midnight-900 px-2 py-1 text-xs text-slate-300">
          {client.anomaly_count} anomal{client.anomaly_count === 1 ? 'y' : 'ies'}:{' '}
          {client.top_anomaly}
        </div>
      )}
    </div>
  )
}

export function PortfolioAnalytics({
  clients,
  summaryStats,
}: PortfolioAnalyticsProps) {
  return (
    <div className="w-full rounded-[14px] border border-midnight-700 bg-midnight-800 p-3">
      {/* Summary row */}
      <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium text-white">
          {summaryStats.total_clients} clients:
        </span>
        <span className="text-[#4a7c59]">
          {summaryStats.sage_count} cruising
        </span>
        <span className="text-[#d97706]">
          {summaryStats.amber_count} calibrating
        </span>
        <span className="text-[#ef4444]">
          {summaryStats.coral_count} attention
        </span>
      </div>

      {/* Client tile grid */}
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-4">
        {clients.map((client) => (
          <ClientTileCard key={client.client_id} client={client} />
        ))}
      </div>
    </div>
  )
}
