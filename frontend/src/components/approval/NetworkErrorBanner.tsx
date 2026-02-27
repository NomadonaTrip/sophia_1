import { WifiOff, RefreshCw } from 'lucide-react'
import { useNetworkError } from '@/hooks/useNetworkError'
import { Button } from '@/components/ui/button'

export function NetworkErrorBanner() {
  const { hasError, retryCount, maxRetries, isRetrying, message, clearError } =
    useNetworkError()

  if (!hasError) return null

  const exhaustedRetries = retryCount >= maxRetries

  return (
    <div
      className="bg-amber-500/10 border-b border-amber-500/30"
      role="alert"
      aria-live="assertive"
    >
      <div className="mx-auto w-[60%] flex items-center gap-3 px-4 py-2">
        <WifiOff className="h-4 w-4 text-amber-400 flex-none" />

        <span className="text-xs text-amber-400 flex-1">
          {exhaustedRetries
            ? 'Unable to connect. Check your network.'
            : isRetrying
              ? `Connection issue — retrying... (${retryCount}/${maxRetries})`
              : message || 'Connection issue detected.'}
        </span>

        <Button
          size="sm"
          variant="ghost"
          onClick={clearError}
          className="text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 h-7 text-xs"
        >
          <RefreshCw className="h-3 w-3 mr-1" />
          Retry
        </Button>
      </div>
    </div>
  )
}
