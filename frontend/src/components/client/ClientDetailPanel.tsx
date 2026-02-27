import { useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { X, TrendingUp, TrendingDown, Minus, Users, Eye, MessageCircle, Target } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { SophiaCommentary } from '@/components/chat/SophiaCommentary'
import { ContentItem, ContentItemSkeleton, type ContentDraft } from '@/components/approval/ContentItem'
import type { ClientData } from '@/components/portfolio/ClientTile'

interface KPI {
  label: string
  value: string
  trend: 'up' | 'down' | 'flat'
  icon: React.ComponentType<{ className?: string }>
}

interface ClientDetailPanelProps {
  client: ClientData | null
  isOpen: boolean
  onClose: () => void
  drafts?: ContentDraft[]
  isLoadingDrafts?: boolean
  diagnosis?: string
  onApprove: (draftId: number) => void
  onReject: (draftId: number, tags: string[], guidance?: string) => void
  onEdit: (draftId: number, copy: string) => void
  onUploadImage: (draftId: number, file: File) => void
  onRecover?: (draftId: number) => void
}

const STATUS_BADGE_VARIANT: Record<string, 'sage' | 'amber' | 'coral'> = {
  cruising: 'sage',
  calibrating: 'amber',
  attention: 'coral',
}

function TrendIndicator({ trend }: { trend: 'up' | 'down' | 'flat' }) {
  switch (trend) {
    case 'up':
      return <TrendingUp className="h-3 w-3 text-sage-400" />
    case 'down':
      return <TrendingDown className="h-3 w-3 text-coral-400" />
    case 'flat':
      return <Minus className="h-3 w-3 text-text-muted" />
  }
}

export function ClientDetailPanel({
  client,
  isOpen,
  onClose,
  drafts = [],
  isLoadingDrafts = false,
  diagnosis,
  onApprove,
  onReject,
  onEdit,
  onUploadImage,
  onRecover,
}: ClientDetailPanelProps) {
  // Escape key to close
  useEffect(() => {
    if (!isOpen) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [isOpen, onClose])

  const handleApprove = useCallback((draftId: number) => onApprove(draftId), [onApprove])
  const handleReject = useCallback((draftId: number, tags: string[], guidance?: string) => onReject(draftId, tags, guidance), [onReject])
  const handleEdit = useCallback((draftId: number, copy: string) => onEdit(draftId, copy), [onEdit])
  const handleUploadImage = useCallback((draftId: number, file: File) => onUploadImage(draftId, file), [onUploadImage])

  if (!client) return null

  // Build KPIs from client data
  const kpis: KPI[] = [
    {
      label: 'Engagement',
      value: `${client.engagementRate}%`,
      trend: client.trend,
      icon: Eye,
    },
    {
      label: 'Posts',
      value: String(client.postCount),
      trend: 'flat',
      icon: MessageCircle,
    },
    {
      label: 'Voice Match',
      value: `${client.voiceMatchPct}%`,
      trend: client.voiceMatchPct >= 80 ? 'up' : client.voiceMatchPct >= 60 ? 'flat' : 'down',
      icon: Target,
    },
    {
      label: 'Followers',
      value: '--',
      trend: 'flat',
      icon: Users,
    },
  ]

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="overflow-hidden"
          role="region"
          aria-label={`${client.name} details`}
        >
          <div className="rounded-[14px] border border-midnight-700 bg-midnight-800 p-4 my-2">
            {/* Header: name, business, status badge, close button */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-medium text-text-primary">
                  {client.name}
                </h3>
                <Badge variant={STATUS_BADGE_VARIANT[client.status]}>
                  {client.status}
                </Badge>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
                aria-label="Close panel"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Metrics row: 4 KPIs */}
            <div className="grid grid-cols-4 gap-3 mb-3">
              {kpis.map((kpi) => {
                const Icon = kpi.icon
                return (
                  <div
                    key={kpi.label}
                    className="rounded-lg bg-midnight-900 border border-midnight-700 p-2 text-center"
                  >
                    <div className="flex items-center justify-center gap-1 mb-1">
                      <Icon className="h-3 w-3 text-text-muted" />
                      <span className="text-base font-medium text-text-primary tabular-nums">
                        {kpi.value}
                      </span>
                      <TrendIndicator trend={kpi.trend} />
                    </div>
                    <span className="text-[10px] text-text-muted uppercase tracking-wide">
                      {kpi.label}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Sophia diagnosis */}
            {diagnosis && (
              <div className="mb-3">
                <SophiaCommentary variant="compact">
                  {diagnosis}
                </SophiaCommentary>
              </div>
            )}

            {/* Content queue */}
            <div>
              <h4 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
                Content Queue
              </h4>

              {isLoadingDrafts ? (
                <div className="space-y-2">
                  <ContentItemSkeleton />
                  <ContentItemSkeleton />
                </div>
              ) : drafts.length > 0 ? (
                <div className="space-y-2">
                  {drafts.map((draft) => (
                    <ContentItem
                      key={draft.id}
                      draft={draft}
                      onApprove={handleApprove}
                      onReject={handleReject}
                      onEdit={handleEdit}
                      onUploadImage={handleUploadImage}
                      onRecover={onRecover ? () => onRecover(draft.id) : undefined}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted text-center py-4">
                  No drafts in queue
                </p>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function ClientDetailPanelSkeleton() {
  return (
    <div className="rounded-[14px] border border-midnight-700 bg-midnight-800 p-4 my-2">
      <div className="flex items-center gap-2 mb-3">
        <div className="skeleton-sage h-5 w-32 rounded" />
        <div className="skeleton-sage h-5 w-16 rounded" />
      </div>
      <div className="grid grid-cols-4 gap-3 mb-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-lg bg-midnight-900 border border-midnight-700 p-2">
            <div className="skeleton-sage h-5 w-12 rounded mx-auto mb-1" />
            <div className="skeleton-sage h-2.5 w-16 rounded mx-auto" />
          </div>
        ))}
      </div>
      <div className="skeleton-sage h-16 w-full rounded mb-3" />
      <div className="space-y-2">
        <ContentItemSkeleton />
      </div>
    </div>
  )
}
