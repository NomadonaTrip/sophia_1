import { useState, useCallback, useRef, type KeyboardEvent } from 'react'
import { motion } from 'motion/react'
import {
  Check,
  X,
  Pencil,
  Upload,
  AlertTriangle,
  Clock,
  BookOpen,
  Mic2,
  Compass,
  Shield,
  Sparkles,
  Search,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { QuickTagSelector } from '@/components/approval/QuickTagSelector'
import { PlatformMockupPreview } from '@/components/approval/PlatformMockupPreview'
import { CopyReadyPackage } from '@/components/approval/CopyReadyPackage'

export interface ContentDraft {
  id: number
  client_id: number
  client_name: string
  platform: 'facebook' | 'instagram'
  copy: string
  image_prompt?: string
  image_url?: string
  hashtags?: string[]
  voice_alignment_pct?: number
  research_source_count?: number
  content_pillar?: string
  scheduled_time?: string
  publish_mode?: 'auto' | 'manual'
  status: 'in_review' | 'approved' | 'rejected' | 'published' | 'recovered'
  regeneration_guidance?: string
  gate_report?: {
    voice_alignment?: { passed: boolean; score?: number }
    research_grounding?: { passed: boolean; score?: number }
    sensitivity?: { passed: boolean }
    originality?: { passed: boolean; score?: number }
  }
  suggested_time?: string
}

interface ContentItemProps {
  draft: ContentDraft
  isFocused?: boolean
  onApprove: (draftId: number) => void
  onReject: (draftId: number, tags: string[], guidance?: string) => void
  onEdit: (draftId: number, copy: string) => void
  onUploadImage: (draftId: number, file: File) => void
  onRecover?: (draftId: number) => void
  onFocus?: () => void
  tabIndex?: number
}

function GateBadge({
  label,
  passed,
  score,
  icon: Icon,
}: {
  label: string
  passed: boolean
  score?: number
  icon: React.ComponentType<{ className?: string }>
}) {
  return (
    <Badge
      variant={passed ? 'sage' : 'coral'}
      className="gap-1 text-[10px] py-0 px-1.5"
    >
      <Icon className="h-2.5 w-2.5" />
      {label}
      {score != null && <span className="tabular-nums">{Math.round(score * 100)}%</span>}
    </Badge>
  )
}

export function ContentItem({
  draft,
  isFocused = false,
  onApprove,
  onReject,
  onEdit,
  onUploadImage,
  onRecover,
  onFocus,
  tabIndex = 0,
}: ContentItemProps) {
  const [isApproved, setIsApproved] = useState(draft.status === 'approved')
  const [showRejectTags, setShowRejectTags] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editCopy, setEditCopy] = useState(draft.copy)
  const [rejectPulse, setRejectPulse] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleApprove = useCallback(() => {
    setIsApproved(true)
    onApprove(draft.id)
  }, [draft.id, onApprove])

  const handleReject = useCallback(() => {
    // Trigger coral border pulse
    setRejectPulse(true)
    setTimeout(() => setRejectPulse(false), 400)
    setShowRejectTags(true)
  }, [])

  const handleRejectSubmit = useCallback(
    (tags: string[], guidance?: string) => {
      onReject(draft.id, tags, guidance)
      setShowRejectTags(false)
    },
    [draft.id, onReject],
  )

  const handleEditSave = useCallback(() => {
    onEdit(draft.id, editCopy)
    setIsEditing(false)
  }, [draft.id, editCopy, onEdit])

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (file) {
        onUploadImage(draft.id, file)
      }
    },
    [draft.id, onUploadImage],
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Enter') {
        onFocus?.()
      }
    },
    [onFocus],
  )

  const hasImage = !!draft.image_url
  const isPublished = draft.status === 'published'
  const isManualPublish = draft.publish_mode === 'manual'

  return (
    <motion.div
      animate={{ opacity: isApproved ? 0.4 : 1 }}
      transition={{ duration: 0.08 }}
      className={cn(
        'rounded-[14px] border bg-midnight-800 overflow-hidden transition-colors',
        isFocused
          ? 'border-sage-500 ring-1 ring-sage-500/30'
          : 'border-midnight-700',
        rejectPulse && 'animate-reject-pulse',
        !hasImage && !isApproved && 'border-l-[3px] border-l-amber-500',
      )}
      role="article"
      aria-label={`Content for ${draft.client_name} on ${draft.platform}`}
      tabIndex={tabIndex}
      onFocus={onFocus}
      onKeyDown={handleKeyDown}
    >
      {/* Header: client name + platform label */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-midnight-700">
        <span className="text-sm font-medium text-text-primary">
          {draft.client_name}
        </span>
        <span className="text-[10px] uppercase tracking-wider text-text-muted font-medium">
          {draft.platform}
        </span>
      </div>

      <div className="p-3 space-y-2.5">
        {/* Quality gate badges */}
        {draft.gate_report && (
          <div className="flex flex-wrap gap-1">
            {draft.gate_report.voice_alignment && (
              <GateBadge
                label="Voice"
                passed={draft.gate_report.voice_alignment.passed}
                score={draft.gate_report.voice_alignment.score}
                icon={Mic2}
              />
            )}
            {draft.gate_report.research_grounding && (
              <GateBadge
                label="Research"
                passed={draft.gate_report.research_grounding.passed}
                score={draft.gate_report.research_grounding.score}
                icon={Search}
              />
            )}
            {draft.gate_report.sensitivity && (
              <GateBadge
                label="Sensitivity"
                passed={draft.gate_report.sensitivity.passed}
                icon={Shield}
              />
            )}
            {draft.gate_report.originality && (
              <GateBadge
                label="Originality"
                passed={draft.gate_report.originality.passed}
                score={draft.gate_report.originality.score}
                icon={Sparkles}
              />
            )}
          </div>
        )}

        {/* Post copy */}
        {isEditing ? (
          <div className="space-y-2">
            <textarea
              value={editCopy}
              onChange={(e) => setEditCopy(e.target.value)}
              className="w-full min-h-[100px] rounded-md border border-midnight-600 bg-midnight-900 px-2.5 py-2 text-sm text-text-primary placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sage-400 resize-y"
              aria-label="Edit post content"
            />
            <div className="flex gap-2">
              <Button size="sm" variant="sage" onClick={handleEditSave}>
                Save
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setIsEditing(false)
                  setEditCopy(draft.copy)
                }}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-text-primary leading-[1.45]">{draft.copy}</p>
        )}

        {/* Content provenance row */}
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-text-muted">
          {draft.voice_alignment_pct != null && (
            <span className="flex items-center gap-1">
              <Mic2 className="h-3 w-3" />
              Voice {draft.voice_alignment_pct}%
            </span>
          )}
          {draft.research_source_count != null && (
            <span className="flex items-center gap-1">
              <BookOpen className="h-3 w-3" />
              {draft.research_source_count} sources
            </span>
          )}
          {draft.content_pillar && (
            <span className="flex items-center gap-1">
              <Compass className="h-3 w-3" />
              {draft.content_pillar}
            </span>
          )}
          {draft.scheduled_time && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {draft.scheduled_time}
            </span>
          )}
        </div>

        {/* Guidance applied label (for regenerated drafts) */}
        {draft.regeneration_guidance && (
          <div className="rounded-md bg-sage-500/10 border border-sage-500/20 px-2 py-1">
            <span className="text-[11px] text-sage-300">
              Guidance applied: {draft.regeneration_guidance}
            </span>
          </div>
        )}

        {/* Platform mockup preview */}
        <PlatformMockupPreview
          platform={draft.platform}
          copy={draft.copy}
          imageUrl={draft.image_url}
          clientName={draft.client_name}
          hashtags={draft.hashtags}
        />

        {/* Image upload area */}
        <div
          className={cn(
            'rounded-md border border-dashed p-2.5 text-center',
            hasImage ? 'border-midnight-600' : 'border-amber-500/50',
          )}
        >
          {hasImage ? (
            <div className="flex items-center gap-2">
              <img
                src={draft.image_url}
                alt="Uploaded"
                className="h-12 w-12 rounded object-cover"
              />
              <span className="text-xs text-text-muted">Image attached</span>
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto h-7 text-xs"
                onClick={() => fileInputRef.current?.click()}
              >
                Replace
              </Button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center justify-center gap-1.5 w-full py-2 text-xs text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
            >
              <Upload className="h-3.5 w-3.5" />
              {draft.image_prompt
                ? `Upload image (prompt: "${draft.image_prompt.slice(0, 40)}...")`
                : 'Upload image'}
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileChange}
            className="hidden"
            aria-label="Upload image"
          />
        </div>

        {/* CopyReadyPackage for manual publish mode (after approval) */}
        {isManualPublish && isApproved && (
          <CopyReadyPackage
            copy={draft.copy}
            imagePrompt={draft.image_prompt}
            hashtags={draft.hashtags}
            suggestedTime={draft.suggested_time}
            platform={draft.platform}
            clientName={draft.client_name}
          />
        )}

        {/* QuickTagSelector (on reject) */}
        {showRejectTags && (
          <QuickTagSelector
            onSubmit={handleRejectSubmit}
            onCancel={() => setShowRejectTags(false)}
          />
        )}

        {/* Approved overlay check */}
        {isApproved && (
          <div className="flex items-center justify-center gap-1.5 py-1">
            <Check className="h-4 w-4 text-sage-400" />
            <span className="text-xs text-sage-300 font-medium">Approved</span>
          </div>
        )}

        {/* Action buttons: three-tier hierarchy */}
        {!isApproved && !isEditing && draft.status !== 'published' && (
          <div className="flex items-center gap-2 pt-1">
            {/* Reject — left, ghost */}
            <Button
              size="sm"
              variant="ghost"
              onClick={handleReject}
              className="text-text-muted hover:text-coral-400 hover:bg-coral-500/10"
            >
              <X className="h-3.5 w-3.5" />
              Reject
            </Button>

            {/* Edit — middle, secondary */}
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setIsEditing(true)}
              className="ml-auto"
            >
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Button>

            {/* Approve — right, sage primary */}
            <Button size="sm" variant="sage" onClick={handleApprove}>
              <Check className="h-3.5 w-3.5" />
              Approve
            </Button>
          </div>
        )}

        {/* Recovery button for published posts */}
        {isPublished && onRecover && (
          <div className="flex justify-end pt-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onRecover(draft.id)}
              className="text-coral-400 hover:text-coral-300 hover:bg-coral-500/10"
            >
              <AlertTriangle className="h-3.5 w-3.5" />
              Recover
            </Button>
          </div>
        )}
      </div>
    </motion.div>
  )
}

/** Skeleton variant for loading state */
export function ContentItemSkeleton() {
  return (
    <div className="rounded-[14px] border border-midnight-700 bg-midnight-800 overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 border-b border-midnight-700">
        <div className="skeleton-sage h-4 w-28 rounded" />
        <div className="skeleton-sage h-3 w-16 rounded" />
      </div>
      <div className="p-3 space-y-2.5">
        <div className="flex gap-1">
          <div className="skeleton-sage h-4 w-14 rounded" />
          <div className="skeleton-sage h-4 w-16 rounded" />
          <div className="skeleton-sage h-4 w-14 rounded" />
        </div>
        <div className="space-y-1.5">
          <div className="skeleton-sage h-3.5 w-full rounded" />
          <div className="skeleton-sage h-3.5 w-full rounded" />
          <div className="skeleton-sage h-3.5 w-3/4 rounded" />
        </div>
        <div className="flex gap-3">
          <div className="skeleton-sage h-3 w-16 rounded" />
          <div className="skeleton-sage h-3 w-20 rounded" />
          <div className="skeleton-sage h-3 w-14 rounded" />
        </div>
        <div className="skeleton-sage h-40 w-full rounded" />
        <div className="flex gap-2 pt-1">
          <div className="skeleton-sage h-8 w-16 rounded" />
          <div className="skeleton-sage h-8 w-14 rounded ml-auto" />
          <div className="skeleton-sage h-8 w-18 rounded" />
        </div>
      </div>
    </div>
  )
}
