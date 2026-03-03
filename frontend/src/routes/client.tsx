import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { ClientDetailPanel } from '@/components/client/ClientDetailPanel'
import { PortfolioGrid } from '@/components/portfolio/PortfolioGrid'
import { RecoveryDialog } from '@/components/approval/RecoveryDialog'
import type { ClientData } from '@/components/portfolio/ClientTile'
import type { ContentDraft } from '@/components/approval/ContentItem'

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
]

export function ClientDrillDown() {
  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['clients'],
    queryFn: () => apiFetch<ClientData[]>('/clients'),
  })

  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [recoveryDraftId, setRecoveryDraftId] = useState<number | null>(null)

  const selectedClient = clients.find((c) => c.id === selectedClientId) ?? null
  const clientDrafts = selectedClientId ? DEMO_DRAFTS.filter((d) => d.client_id === selectedClientId) : []
  const recoveryDraft = recoveryDraftId ? DEMO_DRAFTS.find((d) => d.id === recoveryDraftId) : null

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
        clients={clients}
        selectedClientId={selectedClientId ?? undefined}
        onClientSelect={handleClientSelect}
        isLoading={isLoading}
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
        onRecover={(id) => setRecoveryDraftId(id)}
      />

      {recoveryDraft && (
        <RecoveryDialog
          draftId={recoveryDraft.id}
          clientName={recoveryDraft.client_name}
          platform={recoveryDraft.platform}
          onSubmit={(id, reason, urgency) => {
            console.log('Recovery submitted:', { id, reason, urgency })
            setRecoveryDraftId(null)
          }}
          onClose={() => setRecoveryDraftId(null)}
        />
      )}
    </div>
  )
}
