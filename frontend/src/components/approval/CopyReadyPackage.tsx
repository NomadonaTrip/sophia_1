import { useState, useCallback } from 'react'
import { Copy, Check, Clock, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface CopyReadyPackageProps {
  copy: string
  imagePrompt?: string
  hashtags?: string[]
  suggestedTime?: string
  platform: 'facebook' | 'instagram'
  clientName: string
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [text])

  return (
    <Button
      size="sm"
      variant="ghost"
      onClick={handleCopy}
      className="h-7 text-xs gap-1"
    >
      {copied ? (
        <>
          <Check className="h-3 w-3 text-sage-400" />
          <span className="text-sage-400">Copied!</span>
        </>
      ) : (
        <>
          <Copy className="h-3 w-3" />
          {label && <span>{label}</span>}
        </>
      )}
    </Button>
  )
}

const PLATFORM_NOTES: Record<string, string> = {
  facebook:
    'First 125 characters visible above fold. Links in comments perform better. Tag relevant pages for reach.',
  instagram:
    'Max 30 hashtags. Put hashtags in first comment for cleaner look. @ mentions drive engagement.',
}

export function CopyReadyPackage({
  copy,
  imagePrompt,
  hashtags,
  suggestedTime,
  platform,
  clientName,
}: CopyReadyPackageProps) {
  return (
    <div
      className="rounded-lg border border-midnight-700 bg-midnight-800 border-l-[3px] border-l-sage-500 overflow-hidden"
      role="region"
      aria-label={`Copy-ready package for ${clientName} on ${platform}`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-midnight-700">
        <FileText className="h-3.5 w-3.5 text-sage-400" />
        <span className="text-xs font-medium text-sage-300">
          Ready to Post — {platform === 'facebook' ? 'Facebook' : 'Instagram'}
        </span>
      </div>

      <div className="p-3 space-y-3">
        {/* Copyable text block */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] uppercase tracking-wider text-text-muted">
              Post Copy
            </span>
            <CopyButton text={copy} label="Copy" />
          </div>
          <div className="rounded-md bg-midnight-900 border border-midnight-600 p-2.5 font-mono text-xs text-text-primary leading-[1.5] whitespace-pre-wrap">
            {copy}
          </div>
        </div>

        {/* Image prompt */}
        {imagePrompt && (
          <div>
            <span className="text-[10px] uppercase tracking-wider text-text-secondary block mb-1">
              Image Prompt:
            </span>
            <p className="text-xs text-text-secondary italic">{imagePrompt}</p>
          </div>
        )}

        {/* Hashtags */}
        {hashtags && hashtags.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] uppercase tracking-wider text-text-muted">
                Hashtags
              </span>
              <CopyButton
                text={hashtags
                  .map((h) => (h.startsWith('#') ? h : `#${h}`))
                  .join(' ')}
                label="Copy"
              />
            </div>
            <p className="text-xs text-text-muted">
              {hashtags.map((h) => (h.startsWith('#') ? h : `#${h}`)).join(' ')}
            </p>
          </div>
        )}

        {/* Suggested time */}
        {suggestedTime && (
          <div className="flex items-center gap-1.5">
            <Clock className="h-3 w-3 text-text-muted" />
            <span className="text-xs text-text-muted">
              Suggested: {suggestedTime}
            </span>
          </div>
        )}

        {/* Platform notes */}
        <div className="rounded-md bg-midnight-900/50 px-2.5 py-2 border border-midnight-700">
          <span className="text-[10px] uppercase tracking-wider text-text-muted block mb-0.5">
            {platform === 'facebook' ? 'Facebook' : 'Instagram'} Tips
          </span>
          <p className="text-[11px] text-text-muted leading-[1.4]">
            {PLATFORM_NOTES[platform]}
          </p>
        </div>
      </div>
    </div>
  )
}
