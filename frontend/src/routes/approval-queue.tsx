import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LayoutGrid, List } from 'lucide-react'
import { apiFetch } from '@/lib/api'
import { useApproval } from '@/hooks/useApproval'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { ContentItem, ContentItemSkeleton, type ContentDraft } from '@/components/approval/ContentItem'
import { BatchApprovalGrid } from '@/components/approval/BatchApprovalGrid'
import { Button } from '@/components/ui/button'

type ViewMode = 'individual' | 'batch'

export function ApprovalQueue() {
  const [viewMode, setViewMode] = useState<ViewMode>('individual')
  const [focusedIndex, setFocusedIndex] = useState(0)
  const [rejectTrigger, setRejectTrigger] = useState(0)
  const [editTrigger, setEditTrigger] = useState(0)

  const { approve, reject, edit, uploadImage, recover } = useApproval()

  const {
    data: drafts = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['drafts'],
    queryFn: () => apiFetch<ContentDraft[]>('/approval/queue'),
  })

  // --- Individual mode handlers ---
  const handleApprove = useCallback(
    (draftId: number) => {
      approve.mutate({ draftId })
    },
    [approve],
  )

  const handleReject = useCallback(
    (draftId: number, tags: string[], guidance?: string) => {
      reject.mutate({ draftId, tags, guidance })
    },
    [reject],
  )

  const handleEdit = useCallback(
    (draftId: number, copy: string) => {
      edit.mutate({ draftId, copy })
    },
    [edit],
  )

  const handleUploadImage = useCallback(
    (draftId: number, file: File) => {
      uploadImage.mutate({ draftId, file })
    },
    [uploadImage],
  )

  const handleRecover = useCallback(
    (draftId: number) => {
      recover.mutate({ draftId, reason: 'Operator recovery', urgency: 'review' })
    },
    [recover],
  )

  // --- Batch mode bridge handlers ---
  const handleBatchReject = useCallback(
    (draftId: number) => {
      reject.mutate({ draftId, tags: [] })
    },
    [reject],
  )

  const handleBatchEdit = useCallback(
    (draftId: number) => {
      // Switch to individual mode focused on the draft being edited
      const idx = drafts.findIndex((d) => d.id === draftId)
      setViewMode('individual')
      setFocusedIndex(idx >= 0 ? idx : 0)
      // Trigger edit mode on the focused ContentItem
      setEditTrigger((c) => c + 1)
    },
    [drafts],
  )

  // --- Keyboard shortcuts ---
  useKeyboardShortcuts({
    onApprove: () => {
      const draft = drafts[focusedIndex]
      if (draft) approve.mutate({ draftId: draft.id })
    },
    onReject: () => {
      if (drafts[focusedIndex]) {
        setRejectTrigger((c) => c + 1)
      }
    },
    onEdit: () => {
      if (drafts[focusedIndex]) {
        setEditTrigger((c) => c + 1)
      }
    },
    onNext: () => {
      setFocusedIndex((prev) => (prev < drafts.length - 1 ? prev + 1 : 0))
    },
    onPrev: () => {
      setFocusedIndex((prev) => (prev > 0 ? prev - 1 : drafts.length - 1))
    },
  })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-text-primary mb-1">
            Approval Queue
          </h2>
          <p className="text-xs text-text-muted">
            Review and approve content across your portfolio. Use keyboard shortcuts: A (approve), R (reject), E (edit), N (next).
          </p>
        </div>

        {/* View mode toggle */}
        <div className="flex items-center gap-1 rounded-lg border border-midnight-700 p-0.5">
          <Button
            size="sm"
            variant={viewMode === 'individual' ? 'secondary' : 'ghost'}
            onClick={() => setViewMode('individual')}
            className="h-7 px-2"
            aria-label="Individual view"
          >
            <List className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="sm"
            variant={viewMode === 'batch' ? 'secondary' : 'ghost'}
            onClick={() => setViewMode('batch')}
            className="h-7 px-2"
            aria-label="Batch view"
          >
            <LayoutGrid className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="rounded-lg border border-coral-500/30 bg-coral-500/10 px-3 py-2">
          <p className="text-xs text-coral-300">
            Failed to load drafts. Check your connection and try again.
          </p>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="space-y-3">
          <ContentItemSkeleton />
          <ContentItemSkeleton />
          <ContentItemSkeleton />
        </div>
      )}

      {/* Individual mode: full ContentItem cards */}
      {!isLoading && !isError && viewMode === 'individual' && (
        <div className="space-y-3">
          {drafts.length > 0 ? (
            drafts.map((draft, index) => (
              <ContentItem
                key={draft.id}
                draft={draft}
                isFocused={index === focusedIndex}
                onApprove={handleApprove}
                onReject={handleReject}
                onEdit={handleEdit}
                onUploadImage={handleUploadImage}
                onRecover={handleRecover}
                onFocus={() => setFocusedIndex(index)}
                rejectTrigger={index === focusedIndex ? rejectTrigger : undefined}
                editTrigger={index === focusedIndex ? editTrigger : undefined}
              />
            ))
          ) : (
            <div className="flex items-center justify-center py-12">
              <p className="text-sm text-text-muted">No drafts in queue</p>
            </div>
          )}
        </div>
      )}

      {/* Batch mode: compact grid */}
      {!isLoading && !isError && viewMode === 'batch' && (
        <BatchApprovalGrid
          drafts={drafts}
          onApprove={handleApprove}
          onReject={handleBatchReject}
          onEdit={handleBatchEdit}
        />
      )}
    </div>
  )
}
