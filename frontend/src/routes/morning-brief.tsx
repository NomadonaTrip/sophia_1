import { useState, useCallback, useMemo } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { SophiaCommentary } from '@/components/chat/SophiaCommentary'
import { SessionSummary } from '@/components/session/SessionSummary'
import { PortfolioGrid } from '@/components/portfolio/PortfolioGrid'
import { InsightCard } from '@/components/portfolio/InsightCard'
import { ClientDetailPanel } from '@/components/client/ClientDetailPanel'
import type { ClientData } from '@/components/portfolio/ClientTile'
import type { ContentDraft } from '@/components/approval/ContentItem'

// Demo client data
const DEMO_CLIENTS: ClientData[] = [
  { id: 1, name: "Maple & Main Bakery", status: 'cruising', postCount: 12, engagementRate: 4.2, trend: 'up', voiceMatchPct: 91, sparkline: [3, 4, 3, 5, 4, 5] },
  { id: 2, name: "Shane's Landscaping", status: 'attention', postCount: 3, engagementRate: 1.1, trend: 'down', voiceMatchPct: 72, sparkline: [4, 3, 2, 2, 1, 1] },
  { id: 3, name: "Harbour View Spa", status: 'calibrating', postCount: 8, engagementRate: 3.0, trend: 'flat', voiceMatchPct: 84, sparkline: [3, 3, 4, 3, 3, 3] },
  { id: 4, name: "Peak Fitness Studio", status: 'cruising', postCount: 10, engagementRate: 5.1, trend: 'up', voiceMatchPct: 88, sparkline: [3, 4, 4, 5, 5, 6] },
  { id: 5, name: "Birchwood Dental", status: 'cruising', postCount: 6, engagementRate: 2.8, trend: 'flat', voiceMatchPct: 90, sparkline: [3, 3, 3, 3, 3, 3] },
  { id: 6, name: "Anchor Property Mgmt", status: 'cruising', postCount: 9, engagementRate: 3.5, trend: 'up', voiceMatchPct: 86, sparkline: [2, 3, 3, 4, 3, 4] },
  { id: 7, name: "Lakeside Auto Care", status: 'cruising', postCount: 7, engagementRate: 2.4, trend: 'flat', voiceMatchPct: 93, sparkline: [2, 2, 3, 2, 3, 2] },
  { id: 8, name: "Dundas Valley Vet", status: 'calibrating', postCount: 5, engagementRate: 2.1, trend: 'down', voiceMatchPct: 79, sparkline: [3, 3, 2, 2, 2, 2] },
  { id: 9, name: "Stone Road Accounting", status: 'calibrating', postCount: 4, engagementRate: 1.8, trend: 'flat', voiceMatchPct: 81, sparkline: [2, 2, 2, 2, 2, 2] },
  { id: 10, name: "Waterdown Wellness", status: 'cruising', postCount: 11, engagementRate: 4.7, trend: 'up', voiceMatchPct: 89, sparkline: [3, 4, 4, 5, 5, 5] },
  { id: 11, name: "Binbrook Plumbing", status: 'cruising', postCount: 8, engagementRate: 3.1, trend: 'flat', voiceMatchPct: 87, sparkline: [3, 3, 3, 3, 3, 3] },
  { id: 12, name: "Grimsby Garden Centre", status: 'cruising', postCount: 14, engagementRate: 5.3, trend: 'up', voiceMatchPct: 94, sparkline: [4, 4, 5, 5, 5, 6] },
  { id: 13, name: "Stoney Creek Electric", status: 'cruising', postCount: 6, engagementRate: 2.5, trend: 'flat', voiceMatchPct: 85, sparkline: [2, 3, 2, 3, 2, 3] },
  { id: 14, name: "Ancaster Home Reno", status: 'cruising', postCount: 9, engagementRate: 3.8, trend: 'up', voiceMatchPct: 88, sparkline: [3, 3, 4, 4, 4, 4] },
  { id: 15, name: "Flamborough Farrier", status: 'cruising', postCount: 5, engagementRate: 6.2, trend: 'up', voiceMatchPct: 91, sparkline: [4, 5, 5, 6, 6, 7] },
  { id: 16, name: "Hamilton Harbour Tours", status: 'cruising', postCount: 4, engagementRate: 3.9, trend: 'flat', voiceMatchPct: 82, sparkline: [3, 4, 4, 4, 4, 4] },
]

// Demo drafts per client
const DEMO_DRAFTS: Record<number, ContentDraft[]> = {
  2: [
    {
      id: 201,
      client_id: 2,
      client_name: "Shane's Landscaping",
      platform: 'facebook',
      copy: "Spring is just around the corner. Now's the time to book your seasonal cleanup before the rush hits. We're offering 15% off all early-bird bookings through March.",
      voice_alignment_pct: 72,
      research_source_count: 3,
      content_pillar: 'Seasonal',
      scheduled_time: 'Mon 10:00 AM',
      status: 'in_review',
      gate_report: {
        voice_alignment: { passed: false, score: 0.72 },
        research_grounding: { passed: true, score: 0.85 },
        sensitivity: { passed: true },
        originality: { passed: true, score: 0.91 },
      },
    },
    {
      id: 202,
      client_id: 2,
      client_name: "Shane's Landscaping",
      platform: 'instagram',
      copy: "Before and after from last week's property transformation in Ancaster. Full garden redesign, new stone pathway, and native plantings that'll look even better next spring.",
      image_prompt: "Before/after split photo of a residential garden transformation",
      voice_alignment_pct: 68,
      research_source_count: 1,
      content_pillar: 'Portfolio',
      scheduled_time: 'Wed 12:00 PM',
      status: 'in_review',
      hashtags: ['HamiltonLandscaping', 'GardenDesign', 'BeforeAfter'],
    },
  ],
}

export function MorningBrief() {
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [postsRemaining, setPostsRemaining] = useState(8)
  const [rejectionCounts] = useState<Record<number, number>>({})

  const selectedClient = DEMO_CLIENTS.find((c) => c.id === selectedClientId) ?? null
  const clientDrafts = selectedClientId ? (DEMO_DRAFTS[selectedClientId] ?? []) : []

  const showSessionSummary = postsRemaining === 0

  // Check if any client has 3+ rejections for calibration auto-suggest
  const clientsNeedingCalibration = useMemo(
    () => Object.entries(rejectionCounts).filter(([, count]) => count >= 3).map(([id]) => Number(id)),
    [rejectionCounts],
  )

  const handleClientSelect = useCallback((clientId: number) => {
    setSelectedClientId((prev) => (prev === clientId ? null : clientId))
  }, [])

  const handleClose = useCallback(() => setSelectedClientId(null), [])

  return (
    <div className="flex flex-col gap-4">
      {/* Sophia's morning brief commentary */}
      <SophiaCommentary title="Sophia's Morning Brief">
        <p className="mb-2">
          Good morning, Tayo. Across your portfolio of 16 active clients, 12 are
          cruising with approved content queued through Friday. 3 need
          calibration adjustments based on last week's engagement patterns, and 1
          requires your attention -- Shane's Landscaping has a seasonal pivot
          opportunity I've drafted content around.
        </p>
        <p>
          Today's research surfaced a trending local conversation about spring
          home maintenance in the Hamilton area. I've incorporated this into
          drafts for 4 relevant clients. The approval queue has {postsRemaining} items ready for
          your review.
        </p>
      </SophiaCommentary>

      {/* Compact follow-up */}
      <SophiaCommentary variant="compact">
        Ready when you are. Tap a client card below or ask me about any specific
        account.
      </SophiaCommentary>

      {/* Calibration auto-suggest */}
      {clientsNeedingCalibration.length > 0 && (
        <SophiaCommentary title="Calibration Suggestion" variant="compact">
          I've noticed you've rejected several posts for{' '}
          {DEMO_CLIENTS.find((c) => c.id === clientsNeedingCalibration[0])?.name ?? 'a client'}.
          Would you like to enter calibration, write a manual draft, or skip this post?
        </SophiaCommentary>
      )}

      {/* Insight cards */}
      <div className="flex flex-col gap-2">
        <InsightCard
          type="cross-client"
          label="Trending Topic"
          evidence="Spring home maintenance is trending across Hamilton social channels. 4 of your clients in home services could benefit from timely seasonal content. I've already drafted relevant posts."
          boldHighlights={['Spring home maintenance', '4 of your clients']}
          onReviewDrafts={() => console.log('Review trending drafts')}
          onDismiss={() => console.log('Dismiss insight')}
        />
        <InsightCard
          type="performance"
          label="Engagement Pattern"
          evidence="Posts published between 8-9 AM on weekdays consistently outperform later content by 23% across your portfolio. Consider shifting more scheduling to this window."
          boldHighlights={['8-9 AM', '23%']}
          onDismiss={() => console.log('Dismiss insight')}
        />
      </div>

      {/* Portfolio grid */}
      <PortfolioGrid
        clients={DEMO_CLIENTS}
        selectedClientId={selectedClientId ?? undefined}
        onClientSelect={handleClientSelect}
      />

      {/* Inline client detail panel (expands below grid, no page navigation) */}
      <ClientDetailPanel
        client={selectedClient}
        isOpen={!!selectedClientId}
        onClose={handleClose}
        drafts={clientDrafts}
        diagnosis={
          selectedClientId === 2
            ? "Shane's engagement dropped 40% this month. The seasonal pivot content I drafted targets the spring home maintenance trend that's trending locally. Voice match is at 72% -- could use calibration to better match Shane's direct, no-nonsense tone."
            : undefined
        }
        onApprove={(id) => {
          console.log('Approve:', id)
          setPostsRemaining((p) => Math.max(0, p - 1))
        }}
        onReject={(id, tags, guidance) => console.log('Reject:', id, tags, guidance)}
        onEdit={(id, copy) => console.log('Edit:', id, copy)}
        onUploadImage={(id, file) => console.log('Upload:', id, file.name)}
        onRecover={(id) => console.log('Recover:', id)}
      />

      {/* Session summary auto-appears when queue hits 0 */}
      <AnimatePresence>
        {showSessionSummary && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
            className="mt-4"
          >
            <SessionSummary
              approved={14}
              edited={3}
              regenerated={2}
              calibrated={1}
              sessionTime="12m"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
