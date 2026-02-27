import { useState, useCallback } from 'react'
import { motion } from 'motion/react'
import { Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { BatchApprovalItem } from '@/components/approval/BatchApprovalItem'
import type { ContentDraft } from '@/components/approval/ContentItem'

interface BatchApprovalGridProps {
  drafts: ContentDraft[]
  onApprove: (draftId: number) => void
  onReject: (draftId: number) => void
  onEdit: (draftId: number) => void
}

export function BatchApprovalGrid({
  drafts,
  onApprove,
  onReject,
  onEdit,
}: BatchApprovalGridProps) {
  const [batchApproving, setBatchApproving] = useState(false)
  const [approvedIds, setApprovedIds] = useState<Set<number>>(new Set())

  const handleBatchApprove = useCallback(() => {
    setBatchApproving(true)
    // Stagger approvals with 200ms delay between each
    drafts.forEach((draft, index) => {
      setTimeout(() => {
        setApprovedIds((prev) => new Set([...prev, draft.id]))
        onApprove(draft.id)
      }, index * 200)
    })
  }, [drafts, onApprove])

  const handleSingleApprove = useCallback(
    (draftId: number) => {
      setApprovedIds((prev) => new Set([...prev, draftId]))
      onApprove(draftId)
    },
    [onApprove],
  )

  const pendingCount = drafts.filter((d) => !approvedIds.has(d.id)).length

  return (
    <div>
      {/* Header with batch approve button */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-text-primary">
          Batch Review
        </h3>
        {pendingCount > 0 && (
          <Button
            size="sm"
            variant="sage"
            onClick={handleBatchApprove}
            disabled={batchApproving}
          >
            <Check className="h-3.5 w-3.5" />
            Approve All ({pendingCount})
          </Button>
        )}
      </div>

      {/* 2-column grid */}
      <motion.div
        className="grid grid-cols-1 md:grid-cols-2 gap-2"
        role="list"
        variants={{
          show: { transition: { staggerChildren: 0.2 } },
          hidden: {},
        }}
        initial="hidden"
        animate={batchApproving ? 'show' : 'hidden'}
      >
        {drafts.map((draft) => (
          <BatchApprovalItem
            key={draft.id}
            draft={draft}
            isApproved={approvedIds.has(draft.id)}
            onApprove={handleSingleApprove}
            onReject={onReject}
            onEdit={onEdit}
          />
        ))}
      </motion.div>

      {drafts.length === 0 && (
        <div className="flex items-center justify-center py-8">
          <p className="text-sm text-text-muted">No items in the batch queue</p>
        </div>
      )}
    </div>
  )
}
