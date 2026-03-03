import { useState, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { apiFetch } from '@/lib/api'
import { SophiaCommentary } from '@/components/chat/SophiaCommentary'
import { SessionSummary } from '@/components/session/SessionSummary'
import { PortfolioGrid } from '@/components/portfolio/PortfolioGrid'
import { InsightCard } from '@/components/portfolio/InsightCard'
import { ClientDetailPanel } from '@/components/client/ClientDetailPanel'
import type { ClientData } from '@/components/portfolio/ClientTile'
import type { ContentDraft } from '@/components/approval/ContentItem'

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
    {
      id: 203,
      client_id: 2,
      client_name: "Shane's Landscaping",
      platform: 'facebook',
      copy: "Happy to share this backyard patio project we finished last week in Dundas. Natural flagstone, built-in seating, and low-voltage lighting for those summer evenings.",
      image_prompt: "Completed flagstone patio at dusk with warm low-voltage lighting",
      voice_alignment_pct: 89,
      research_source_count: 2,
      content_pillar: 'Portfolio',
      scheduled_time: 'Fri 9:00 AM',
      status: 'published',
    },
  ],
}

export function MorningBrief() {
  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['clients'],
    queryFn: () => apiFetch<ClientData[]>('/clients'),
  })

  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [postsRemaining, setPostsRemaining] = useState(8)
  const [rejectionCounts] = useState<Record<number, number>>({})

  const selectedClient = clients.find((c) => c.id === selectedClientId) ?? null
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
          {clients.find((c) => c.id === clientsNeedingCalibration[0])?.name ?? 'a client'}.
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
        clients={clients}
        selectedClientId={selectedClientId ?? undefined}
        onClientSelect={handleClientSelect}
        isLoading={isLoading}
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
