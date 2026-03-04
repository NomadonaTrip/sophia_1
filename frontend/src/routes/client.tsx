import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { ClientDetailPanel } from '@/components/client/ClientDetailPanel'
import { PortfolioGrid } from '@/components/portfolio/PortfolioGrid'
import { RecoveryDialog } from '@/components/approval/RecoveryDialog'
import type { ClientData } from '@/components/portfolio/ClientTile'
import type { ContentDraft } from '@/components/approval/ContentItem'

export function ClientDrillDown() {
  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['clients'],
    queryFn: () => apiFetch<ClientData[]>('/clients'),
  })

  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [recoveryDraftId, setRecoveryDraftId] = useState<number | null>(null)

  const { data: clientDrafts = [], isLoading: isLoadingDrafts } = useQuery({
    queryKey: ['client-drafts', selectedClientId],
    queryFn: () => apiFetch<ContentDraft[]>(`/approval/queue?client_id=${selectedClientId}`),
    enabled: selectedClientId !== null,
  })

  const selectedClient = clients.find((c) => c.id === selectedClientId) ?? null
  const recoveryDraft = recoveryDraftId ? clientDrafts.find((d) => d.id === recoveryDraftId) : null

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
        isLoadingDrafts={isLoadingDrafts}
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
