import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface SophiaCommentaryProps {
  title?: string
  variant?: 'standard' | 'compact'
  children: ReactNode
}

function SophiaCommentarySkeleton({
  variant = 'standard',
}: {
  variant?: 'standard' | 'compact'
}) {
  return (
    <div
      className={cn(
        'rounded-[14px] border border-midnight-700 bg-midnight-800 border-l-[3px] border-l-sage-500',
        variant === 'standard' ? 'p-3' : 'p-2',
      )}
      role="article"
      aria-label="Loading commentary"
    >
      <div className="skeleton-sage h-4 w-40 rounded mb-2" />
      {variant === 'standard' && (
        <>
          <div className="skeleton-sage h-3 w-full rounded mb-1.5" />
          <div className="skeleton-sage h-3 w-3/4 rounded" />
        </>
      )}
    </div>
  )
}

export function SophiaCommentary({
  title = "Sophia",
  variant = 'standard',
  children,
}: SophiaCommentaryProps) {
  return (
    <div
      className={cn(
        'relative rounded-[14px] border border-midnight-700 bg-midnight-800 border-l-[3px] border-l-sage-500 overflow-hidden',
        variant === 'standard' ? 'p-3' : 'p-2',
      )}
      role="article"
      aria-label="Sophia's commentary"
    >
      {variant === 'standard' && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(ellipse at 0% 0%, rgba(74,124,89,0.08), transparent 50%)',
          }}
        />
      )}

      <div className="relative">
        <h3
          className={cn(
            'font-sophia italic text-sage-300',
            variant === 'standard' ? 'text-[16px] mb-2' : 'text-sm mb-1',
          )}
        >
          {title}
        </h3>

        <div className="text-sm text-text-primary leading-[1.45]">
          {children}
        </div>
      </div>
    </div>
  )
}

export { SophiaCommentarySkeleton }
