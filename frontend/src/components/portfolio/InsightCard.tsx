import { useState } from 'react'
import { Zap, Lightbulb, TrendingUp } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

type InsightType = 'cross-client' | 'recommendation' | 'performance'

interface InsightCardProps {
  type: InsightType
  label: string
  evidence: string
  boldHighlights?: string[]
  onReviewDrafts?: () => void
  onDismiss?: () => void
  onAskSophia?: () => void
}

const ICONS: Record<InsightType, React.ComponentType<{ className?: string }>> = {
  'cross-client': Zap,
  recommendation: Lightbulb,
  performance: TrendingUp,
}

const LABELS: Record<InsightType, string> = {
  'cross-client': 'Cross-Client Pattern',
  recommendation: 'Recommendation',
  performance: 'Performance Insight',
}

function highlightText(text: string, highlights?: string[]): React.ReactNode {
  if (!highlights || highlights.length === 0) return text

  let result: React.ReactNode[] = []
  let remaining = text
  let keyIndex = 0

  for (const highlight of highlights) {
    const idx = remaining.toLowerCase().indexOf(highlight.toLowerCase())
    if (idx === -1) continue

    if (idx > 0) {
      result.push(remaining.slice(0, idx))
    }
    result.push(
      <strong key={keyIndex++} className="text-text-primary font-medium">
        {remaining.slice(idx, idx + highlight.length)}
      </strong>,
    )
    remaining = remaining.slice(idx + highlight.length)
  }
  if (remaining) result.push(remaining)

  return result.length > 0 ? result : text
}

export function InsightCard({
  type,
  label,
  evidence,
  boldHighlights,
  onReviewDrafts,
  onDismiss,
  onAskSophia,
}: InsightCardProps) {
  const [dismissed, setDismissed] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const Icon = ICONS[type]
  const categoryLabel = label || LABELS[type]

  const handleDismiss = () => {
    setDismissed(true)
    setTimeout(() => onDismiss?.(), 200)
  }

  return (
    <AnimatePresence>
      {!dismissed && (
        <motion.div
          initial={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="rounded-[14px] border border-sage-500/20 bg-midnight-800 p-3 overflow-hidden"
          role="article"
          aria-expanded={expanded}
        >
          {/* Icon + category label */}
          <div className="flex items-center gap-2 mb-2">
            <div className="h-7 w-7 rounded-lg bg-sage-500/10 flex items-center justify-center">
              <Icon className="h-4 w-4 text-sage-400" />
            </div>
            <span className="font-sophia italic text-sm text-sage-300">
              {categoryLabel}
            </span>
          </div>

          {/* Evidence text */}
          <p className="text-sm text-text-secondary leading-[1.45] mb-2.5">
            {highlightText(evidence, boldHighlights)}
          </p>

          {/* Expanded content slot */}
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="mb-2.5"
              >
                <div className="rounded-md bg-midnight-900 border border-midnight-700 p-2.5">
                  <p className="text-xs text-text-muted">
                    Detailed analysis and drafted content will appear here.
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {onReviewDrafts && (
              <Button
                size="sm"
                variant="sage"
                onClick={() => {
                  setExpanded(!expanded)
                  onReviewDrafts()
                }}
              >
                Review Drafts
              </Button>
            )}
            {onAskSophia && (
              <Button size="sm" variant="secondary" onClick={onAskSophia}>
                Ask Sophia
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={handleDismiss}
              className={cn(onReviewDrafts ? 'ml-auto' : '')}
            >
              Dismiss
            </Button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
