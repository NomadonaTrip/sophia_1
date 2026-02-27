import { useState, useEffect, useCallback } from 'react'
import { X, Clock } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'

interface StaleToast {
  id: string
  draftId: number
  clientName: string
  hoursStale: number
}

export function StaleContentToastContainer() {
  const [toasts, setToasts] = useState<StaleToast[]>([])

  useEffect(() => {
    function handleStaleEvent(e: Event) {
      const detail = (e as CustomEvent).detail as {
        draftId: number
        clientName: string
        hoursStale: number
      }

      const id = `stale-${detail.draftId}-${Date.now()}`
      const toast: StaleToast = { id, ...detail }

      setToasts((prev) => [...prev, toast])

      // Auto-dismiss after 10 seconds
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 10_000)
    }

    window.addEventListener('sophia:stale-content', handleStaleEvent)
    return () =>
      window.removeEventListener('sophia:stale-content', handleStaleEvent)
  }, [])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <div className="fixed top-20 right-4 z-50 flex flex-col gap-2 max-w-sm">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            transition={{ duration: 0.2 }}
            className="rounded-lg border border-midnight-700 bg-midnight-800 border-l-[3px] border-l-amber-500 p-3 shadow-lg"
            role="alert"
          >
            <div className="flex items-start gap-2">
              <Clock className="h-4 w-4 text-amber-400 flex-none mt-0.5" />
              <div className="flex-1">
                <p className="text-xs text-amber-400">
                  Draft #{toast.draftId} for {toast.clientName} has been in review
                  for {toast.hoursStale}h
                </p>
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                className="flex-none text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
                aria-label="Dismiss"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
