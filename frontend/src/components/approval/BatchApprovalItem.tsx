import { useState, useCallback, useEffect } from 'react'
import { motion } from 'motion/react'
import { Check, X, Pencil, Clock, Mic2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { ContentDraft } from '@/components/approval/ContentItem'

interface BatchApprovalItemProps {
  draft: ContentDraft
  isApproved?: boolean
  onApprove: (draftId: number) => void
  onReject: (draftId: number) => void
  onEdit: (draftId: number) => void
}

export function BatchApprovalItem({
  draft,
  isApproved = false,
  onApprove,
  onReject,
  onEdit,
}: BatchApprovalItemProps) {
  const [localApproved, setLocalApproved] = useState(isApproved)

  // Sync parent prop to local state (fixes batch fade on "Approve All")
  useEffect(() => {
    setLocalApproved(isApproved)
  }, [isApproved])

  const handleApprove = useCallback(() => {
    setLocalApproved(true)
    onApprove(draft.id)
  }, [draft.id, onApprove])

  return (
    <motion.div
      animate={{ opacity: localApproved ? 0.4 : 1 }}
      transition={{ duration: 0.08 }}
      className={cn(
        'rounded-lg border border-midnight-700 bg-midnight-800 p-2.5',
        localApproved && 'relative',
      )}
      role="listitem"
      aria-label={`${draft.client_name} ${draft.platform} content`}
    >
      {/* Header: client name + platform */}
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-text-primary truncate">
          {draft.client_name}
        </span>
        <span className="text-[9px] uppercase tracking-wider text-text-muted flex-none ml-2">
          {draft.platform}
        </span>
      </div>

      {/* 2-line content preview */}
      <p className="text-xs text-text-secondary leading-[1.4] line-clamp-2 mb-1.5">
        {draft.copy}
      </p>

      {/* Metrics row: voice %, scheduled time */}
      <div className="flex items-center gap-2 text-[10px] text-text-muted mb-2">
        {draft.voice_alignment_pct != null && (
          <span className="flex items-center gap-0.5">
            <Mic2 className="h-2.5 w-2.5" />
            {draft.voice_alignment_pct}%
          </span>
        )}
        {draft.scheduled_time && (
          <span className="flex items-center gap-0.5">
            <Clock className="h-2.5 w-2.5" />
            {draft.scheduled_time}
          </span>
        )}
      </div>

      {/* Approved overlay */}
      {localApproved && (
        <div className="flex items-center justify-center gap-1 py-0.5">
          <Check className="h-3 w-3 text-sage-400" />
          <span className="text-[10px] text-sage-300">Approved</span>
        </div>
      )}

      {/* Action buttons (compact three-tier) */}
      {!localApproved && (
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onReject(draft.id)}
            className="h-6 px-1.5 text-[10px] text-text-muted hover:text-coral-400"
          >
            <X className="h-3 w-3" />
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onEdit(draft.id)}
            className="h-6 px-1.5 text-[10px] ml-auto"
          >
            <Pencil className="h-3 w-3" />
          </Button>
          <Button
            size="sm"
            variant="sage"
            onClick={handleApprove}
            className="h-6 px-1.5 text-[10px]"
          >
            <Check className="h-3 w-3" />
          </Button>
        </div>
      )}
    </motion.div>
  )
}
