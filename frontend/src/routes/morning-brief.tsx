import { useState, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { apiFetch } from '@/lib/api'
import { SophiaCommentary } from '@/components/chat/SophiaCommentary'
import { SessionSummary } from '@/components/session/SessionSummary'
import { PortfolioGrid } from '@/components/portfolio/PortfolioGrid'
import { ClientDetailPanel } from '@/components/client/ClientDetailPanel'
import type { ClientData } from '@/components/portfolio/ClientTile'
import type { ContentDraft } from '@/components/approval/ContentItem'

interface AnalyticsSummary {
  commentary: string
}

export function MorningBrief() {
  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['clients'],
    queryFn: () => apiFetch<ClientData[]>('/clients'),
  })

  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [rejectionCounts] = useState<Record<number, number>>({})
  const [sessionApprovals, setSessionApprovals] = useState(0)
  const [sessionStats, setSessionStats] = useState({
    approved: 0,
    edited: 0,
    regenerated: 0,
  })

  // Portfolio-wide approval queue
  const { data: approvalQueue = [] } = useQuery({
    queryKey: ['approval-queue'],
    queryFn: () => apiFetch<ContentDraft[]>('/approval/queue'),
  })
  const queueTotal = approvalQueue.filter((d) => d.status === 'in_review').length
  const postsRemaining = Math.max(0, queueTotal - sessionApprovals)

  // Per-client drafts
  const { data: clientDrafts = [] } = useQuery({
    queryKey: ['client-drafts', selectedClientId],
    queryFn: () => apiFetch<ContentDraft[]>(`/approval/queue?client_id=${selectedClientId}`),
    enabled: selectedClientId !== null,
  })

  // Per-client analytics commentary
  const { data: clientAnalytics } = useQuery({
    queryKey: ['client-analytics', selectedClientId],
    queryFn: () => apiFetch<AnalyticsSummary>(`/analytics/${selectedClientId}/summary`),
    enabled: selectedClientId !== null,
  })

  const selectedClient = clients.find((c) => c.id === selectedClientId) ?? null

  const showSessionSummary = postsRemaining === 0 && queueTotal > 0

  // Portfolio stats derived from clients
  const cruisingCount = clients.filter((c) => c.status === 'cruising').length
  const calibratingCount = clients.filter((c) => c.status === 'calibrating').length
  const attentionClients = clients.filter((c) => c.status === 'attention')

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
        {isLoading ? (
          <p className="text-text-muted">Loading portfolio data...</p>
        ) : clients.length === 0 ? (
          <p>Good morning, Tayo. No active clients in the portfolio yet.</p>
        ) : (
          <>
            <p className="mb-2">
              Good morning, Tayo. Across your portfolio of{' '}
              <strong>{clients.length}</strong> active client{clients.length !== 1 && 's'},{' '}
              <strong>{cruisingCount}</strong> {cruisingCount === 1 ? 'is' : 'are'} cruising
              {calibratingCount > 0 && (
                <>, <strong>{calibratingCount}</strong> need{calibratingCount === 1 ? 's' : ''} calibration</>
              )}
              {attentionClients.length > 0 && (
                <>, and <strong>{attentionClients.length}</strong> require{attentionClients.length === 1 ? 's' : ''} attention
                  {' \u2014 '}
                  {attentionClients.map((c) => c.name).join(', ')}
                </>
              )}
              .
            </p>
            <p>
              The approval queue has <strong>{postsRemaining}</strong> item{postsRemaining !== 1 && 's'} ready
              for your review.
            </p>
          </>
        )}
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
        diagnosis={clientAnalytics?.commentary || undefined}
        onApprove={(id) => {
          console.log('Approve:', id)
          setSessionApprovals((n) => n + 1)
          setSessionStats((s) => ({ ...s, approved: s.approved + 1 }))
        }}
        onReject={(id, tags, guidance) => {
          console.log('Reject:', id, tags, guidance)
          setSessionStats((s) => ({ ...s, regenerated: s.regenerated + 1 }))
        }}
        onEdit={(id, copy) => {
          console.log('Edit:', id, copy)
          setSessionStats((s) => ({ ...s, edited: s.edited + 1 }))
        }}
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
              approved={sessionStats.approved}
              edited={sessionStats.edited}
              regenerated={sessionStats.regenerated}
              calibrated={0}
              sessionTime=""
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
