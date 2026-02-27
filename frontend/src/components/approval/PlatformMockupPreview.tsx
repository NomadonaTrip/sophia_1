import { Heart, MessageCircle, Share2, Bookmark, ThumbsUp } from 'lucide-react'
import { cn } from '@/lib/utils'

interface PlatformMockupPreviewProps {
  platform: 'facebook' | 'instagram'
  copy: string
  imageUrl?: string
  clientName: string
  hashtags?: string[]
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max) + '...See More'
}

function FacebookMockup({
  copy,
  imageUrl,
  clientName,
}: Omit<PlatformMockupPreviewProps, 'platform' | 'hashtags'>) {
  return (
    <div className="space-y-0">
      {/* Page header */}
      <div className="flex items-center gap-2 p-2.5">
        <div className="h-8 w-8 rounded-full bg-midnight-600 flex items-center justify-center text-text-muted text-xs font-medium">
          {clientName.charAt(0)}
        </div>
        <div>
          <p className="text-xs font-medium text-text-primary">{clientName}</p>
          <p className="text-[10px] text-text-muted">Just now</p>
        </div>
      </div>

      {/* Post text */}
      <div className="px-2.5 pb-2">
        <p className="text-xs text-text-primary leading-[1.4]">
          {truncate(copy, 125)}
        </p>
      </div>

      {/* Image placeholder */}
      <div className="aspect-video bg-midnight-600 flex items-center justify-center">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt="Post preview"
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="text-[10px] text-text-muted">Image placeholder</span>
        )}
      </div>

      {/* Engagement bar */}
      <div className="flex items-center justify-between px-3 py-2 border-t border-midnight-600">
        <div className="flex items-center gap-1 text-text-muted">
          <ThumbsUp className="h-3 w-3" />
          <span className="text-[10px]">Like</span>
        </div>
        <div className="flex items-center gap-1 text-text-muted">
          <MessageCircle className="h-3 w-3" />
          <span className="text-[10px]">Comment</span>
        </div>
        <div className="flex items-center gap-1 text-text-muted">
          <Share2 className="h-3 w-3" />
          <span className="text-[10px]">Share</span>
        </div>
      </div>
    </div>
  )
}

function InstagramMockup({
  copy,
  imageUrl,
  clientName,
  hashtags,
}: Omit<PlatformMockupPreviewProps, 'platform'>) {
  return (
    <div className="space-y-0">
      {/* Username header */}
      <div className="flex items-center gap-2 p-2.5">
        <div className="h-7 w-7 rounded-full bg-midnight-600 flex items-center justify-center text-text-muted text-[10px] font-medium">
          {clientName.charAt(0)}
        </div>
        <p className="text-xs font-medium text-text-primary">
          {clientName.toLowerCase().replace(/\s+/g, '')}
        </p>
      </div>

      {/* Image placeholder (square) */}
      <div className="aspect-square bg-midnight-600 flex items-center justify-center">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt="Post preview"
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="text-[10px] text-text-muted">Image placeholder</span>
        )}
      </div>

      {/* Action icons row */}
      <div className="flex items-center justify-between px-2.5 py-2">
        <div className="flex items-center gap-3">
          <Heart className="h-4 w-4 text-text-muted" />
          <MessageCircle className="h-4 w-4 text-text-muted" />
          <Share2 className="h-4 w-4 text-text-muted" />
        </div>
        <Bookmark className="h-4 w-4 text-text-muted" />
      </div>

      {/* Caption preview */}
      <div className="px-2.5 pb-2">
        <p className="text-xs text-text-primary leading-[1.4]">
          <span className="font-medium">
            {clientName.toLowerCase().replace(/\s+/g, '')}
          </span>{' '}
          {truncate(copy, 125)}
        </p>
        {hashtags && hashtags.length > 0 && (
          <p className="text-xs text-text-muted mt-1">
            {hashtags.map((h) => (h.startsWith('#') ? h : `#${h}`)).join(' ')}
          </p>
        )}
      </div>
    </div>
  )
}

export function PlatformMockupPreview({
  platform,
  copy,
  imageUrl,
  clientName,
  hashtags,
}: PlatformMockupPreviewProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-midnight-700 bg-midnight-800 overflow-hidden',
      )}
      role="img"
      aria-label={`Preview of post on ${platform}`}
    >
      {/* Platform label */}
      <div className="px-2.5 py-1.5 border-b border-midnight-700">
        <span className="text-[10px] uppercase tracking-wider text-text-muted font-medium">
          {platform === 'facebook' ? 'Facebook Preview' : 'Instagram Preview'}
        </span>
      </div>

      {platform === 'facebook' ? (
        <FacebookMockup copy={copy} imageUrl={imageUrl} clientName={clientName} />
      ) : (
        <InstagramMockup
          copy={copy}
          imageUrl={imageUrl}
          clientName={clientName}
          hashtags={hashtags}
        />
      )}
    </div>
  )
}
