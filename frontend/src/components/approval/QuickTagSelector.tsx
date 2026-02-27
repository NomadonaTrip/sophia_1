import { useState, useCallback } from 'react'
import { Check, Tag } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

const PRESET_TAGS = [
  'Too Formal',
  'Too Casual',
  'Wrong Angle',
  'Off-Brand',
  'Too Long',
  'Too Short',
] as const

interface QuickTagSelectorProps {
  onSubmit: (tags: string[], guidance?: string) => void
  onCancel: () => void
}

export function QuickTagSelector({ onSubmit, onCancel }: QuickTagSelectorProps) {
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set())
  const [guidance, setGuidance] = useState('')

  const toggleTag = useCallback((tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev)
      if (next.has(tag)) {
        next.delete(tag)
      } else {
        next.add(tag)
      }
      return next
    })
  }, [])

  const handleSubmit = useCallback(() => {
    const tags = Array.from(selectedTags)
    onSubmit(tags, guidance.trim() || undefined)
  }, [selectedTags, guidance, onSubmit])

  return (
    <div
      className="mt-2 rounded-lg border border-midnight-600 bg-midnight-900 p-3"
      role="group"
      aria-label="Quick feedback tags"
    >
      {/* Label */}
      <div className="flex items-center gap-1.5 mb-2">
        <Tag className="h-3.5 w-3.5 text-text-muted" />
        <span className="text-xs text-text-muted font-medium">Quick feedback</span>
      </div>

      {/* Tag buttons */}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {PRESET_TAGS.map((tag) => {
          const isSelected = selectedTags.has(tag)
          return (
            <button
              key={tag}
              type="button"
              role="button"
              aria-pressed={isSelected}
              onClick={() => toggleTag(tag)}
              className={cn(
                'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors cursor-pointer',
                isSelected
                  ? 'bg-sage-500/20 text-sage-300 border border-sage-500'
                  : 'bg-midnight-800 text-text-muted border border-midnight-600 hover:border-sage-600 hover:text-text-secondary',
              )}
            >
              {isSelected && <Check className="h-3 w-3" />}
              {tag}
            </button>
          )
        })}
      </div>

      {/* Optional guidance text */}
      <textarea
        value={guidance}
        onChange={(e) => setGuidance(e.target.value)}
        placeholder="Additional guidance (optional)..."
        className="w-full h-16 rounded-md border border-midnight-600 bg-midnight-800 px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sage-400 resize-none"
        aria-label="Additional guidance"
      />

      {/* Actions */}
      <div className="flex items-center gap-2 mt-2">
        <Button
          size="sm"
          variant="sage"
          onClick={handleSubmit}
          disabled={selectedTags.size === 0 && !guidance.trim()}
        >
          Submit Feedback
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  )
}
