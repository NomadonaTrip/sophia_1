import { useState, useCallback } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { Button } from '@/components/ui/button'

interface RecoveryDialogProps {
  draftId: number
  clientName: string
  platform: string
  onSubmit: (draftId: number, reason: string, urgency: 'immediate' | 'review') => void
  onClose: () => void
}

export function RecoveryDialog({
  draftId,
  clientName,
  platform,
  onSubmit,
  onClose,
}: RecoveryDialogProps) {
  const [reason, setReason] = useState('')
  const [urgency, setUrgency] = useState<'immediate' | 'review'>('immediate')

  const handleSubmit = useCallback(() => {
    if (!reason.trim()) return
    onSubmit(draftId, reason.trim(), urgency)
    onClose()
  }, [draftId, reason, urgency, onSubmit, onClose])

  return (
    <AnimatePresence>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 bg-midnight-950/80 flex items-center justify-center p-4"
        onClick={onClose}
      >
        {/* Dialog */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.2 }}
          className="w-full max-w-md rounded-[14px] border border-midnight-700 bg-midnight-800 p-5 shadow-xl"
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-label={`Recover post for ${clientName} on ${platform}`}
          aria-modal="true"
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-coral-400" />
              <h2 className="text-base font-medium text-text-primary">
                Recover Post
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <p className="text-xs text-text-muted mb-3">
            {clientName} - {platform}
          </p>

          {/* Reason input */}
          <div className="mb-3">
            <label
              htmlFor="recovery-reason"
              className="block text-xs text-text-secondary mb-1"
            >
              Why should this post be recovered?
            </label>
            <textarea
              id="recovery-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe the issue..."
              className="w-full min-h-[80px] rounded-md border border-midnight-600 bg-midnight-900 px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sage-400 resize-y"
              required
            />
          </div>

          {/* Urgency selector */}
          <div className="mb-4">
            <span className="block text-xs text-text-secondary mb-2">Urgency</span>
            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="urgency"
                  value="immediate"
                  checked={urgency === 'immediate'}
                  onChange={() => setUrgency('immediate')}
                  className="accent-coral-500"
                />
                <span className="text-sm text-text-primary">Remove now</span>
                <span className="text-[10px] text-text-muted">(immediate)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="urgency"
                  value="review"
                  checked={urgency === 'review'}
                  onChange={() => setUrgency('review')}
                  className="accent-amber-500"
                />
                <span className="text-sm text-text-primary">Review for removal</span>
                <span className="text-[10px] text-text-muted">(review)</span>
              </label>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 justify-end">
            <Button size="sm" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={handleSubmit}
              disabled={!reason.trim()}
            >
              Recover Post
            </Button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
