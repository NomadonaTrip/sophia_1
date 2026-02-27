import { useState, useCallback } from 'react'
import { ClientDetailPanel } from '@/components/client/ClientDetailPanel'
import { PortfolioGrid } from '@/components/portfolio/PortfolioGrid'
import type { ClientData } from '@/components/portfolio/ClientTile'
import type { ContentDraft } from '@/components/approval/ContentItem'

// Demo client data
const DEMO_CLIENTS: ClientData[] = [
  { id: 1, name: "Maple & Main Bakery", status: 'cruising', postCount: 12, engagementRate: 4.2, trend: 'up', voiceMatchPct: 91, sparkline: [3, 4, 3, 5, 4, 5] },
  { id: 2, name: "Shane's Landscaping", status: 'attention', postCount: 3, engagementRate: 1.1, trend: 'down', voiceMatchPct: 72, sparkline: [4, 3, 2, 2, 1, 1] },
  { id: 3, name: "Harbour View Spa", status: 'calibrating', postCount: 8, engagementRate: 3.0, trend: 'flat', voiceMatchPct: 84, sparkline: [3, 3, 4, 3, 3, 3] },
  { id: 4, name: "Peak Fitness Studio", status: 'cruising', postCount: 10, engagementRate: 5.1, trend: 'up', voiceMatchPct: 88, sparkline: [3, 4, 4, 5, 5, 6] },
  { id: 5, name: "Birchwood Dental", status: 'cruising', postCount: 6, engagementRate: 2.8, trend: 'flat', voiceMatchPct: 90, sparkline: [3, 3, 3, 3, 3, 3] },
]

// Demo drafts for selected client
const DEMO_DRAFTS: ContentDraft[] = [
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
]

export function ClientDrillDown() {
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)

  const selectedClient = DEMO_CLIENTS.find((c) => c.id === selectedClientId) ?? null
  const clientDrafts = selectedClientId ? DEMO_DRAFTS.filter((d) => d.client_id === selectedClientId) : []

  const handleClientSelect = useCallback((clientId: number) => {
    setSelectedClientId((prev) => (prev === clientId ? null : clientId))
  }, [])

  const handleClose = useCallback(() => setSelectedClientId(null), [])

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-medium text-text-primary mb-1">
          Client Drill-Down
        </h2>
        <p className="text-xs text-text-muted">
          Click a client tile to expand their detail panel inline.
        </p>
      </div>

      <PortfolioGrid
        clients={DEMO_CLIENTS}
        selectedClientId={selectedClientId ?? undefined}
        onClientSelect={handleClientSelect}
      />

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
        onApprove={(id) => console.log('Approve:', id)}
        onReject={(id, tags, guidance) => console.log('Reject:', id, tags, guidance)}
        onEdit={(id, copy) => console.log('Edit:', id, copy)}
        onUploadImage={(id, file) => console.log('Upload:', id, file.name)}
        onRecover={(id) => console.log('Recover:', id)}
      />
    </div>
  )
}
