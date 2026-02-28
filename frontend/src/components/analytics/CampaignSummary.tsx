/**
 * Campaign performance summary card for chat stream analytics.
 *
 * Displays campaign-level metrics: post count, total reach, avg engagement rate.
 * Renders inline at full chat width in the Midnight Sage design system.
 */

import { cn } from '@/lib/utils'

interface CampaignSummaryProps {
  name: string
  postCount: number
  totalReach: number
  totalEngagement: number
  avgEngagementRate: number
  dateRange: string
  contentPillar?: string
}

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}k`
  return String(num)
}

export function CampaignSummary({
  name,
  postCount,
  totalReach,
  totalEngagement: _totalEngagement,
  avgEngagementRate,
  dateRange,
  contentPillar,
}: CampaignSummaryProps) {
  // Clamp engagement rate for progress bar (max 20% display)
  const progressPct = Math.min(avgEngagementRate * 100, 20) * 5 // scale to 0-100%

  return (
    <div className="w-full rounded-xl border border-midnight-700 bg-midnight-800 p-4">
      {/* Header */}
      <div className="mb-3">
        <h4 className="text-base font-semibold text-white">{name}</h4>
        <p className="text-xs text-slate-400">
          {dateRange}
          {contentPillar && (
            <span
              className={cn(
                'ml-2 inline-block rounded-full bg-midnight-700 px-2 py-0.5 text-xs text-sage-300',
              )}
            >
              {contentPillar}
            </span>
          )}
        </p>
      </div>

      {/* Stats row */}
      <div className="mb-3 grid grid-cols-3 gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">
            Posts
          </p>
          <p className="text-lg font-bold text-white">{postCount}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">
            Reach
          </p>
          <p className="text-lg font-bold text-white">
            {formatNumber(totalReach)}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400">
            Avg ER
          </p>
          <p className="text-lg font-bold text-white">
            {(avgEngagementRate * 100).toFixed(1)}%
          </p>
        </div>
      </div>

      {/* Engagement rate progress bar */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-midnight-700">
        <div
          className="h-full rounded-full bg-[#4a7c59] transition-all"
          style={{ width: `${progressPct}%` }}
        />
      </div>
    </div>
  )
}
