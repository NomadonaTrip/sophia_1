import { SophiaCommentary } from '@/components/chat/SophiaCommentary'
import { SessionSummary } from '@/components/session/SessionSummary'

export function MorningBrief() {
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
          drafts for 4 relevant clients. The approval queue has 8 items ready for
          your review.
        </p>
      </SophiaCommentary>

      {/* Compact follow-up */}
      <SophiaCommentary variant="compact">
        Ready when you are. Tap a client card below or ask me about any specific
        account.
      </SophiaCommentary>

      {/* Portfolio grid placeholder */}
      <div className="rounded-[14px] border border-midnight-700 bg-midnight-800 p-6 text-center">
        <p className="text-text-muted text-sm">Portfolio grid coming soon</p>
      </div>

      {/* Session summary demo */}
      <div className="mt-4">
        <SessionSummary
          approved={14}
          edited={3}
          regenerated={2}
          calibrated={1}
          sessionTime="12m"
        />
      </div>
    </div>
  )
}
