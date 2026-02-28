/**
 * Voice command feedback toast.
 *
 * Shows a brief on-screen text notification for voice command results.
 * Visual feedback only -- no TTS. Auto-dismisses after 3 seconds.
 */

import { useState, useEffect, useCallback } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Mic, X } from 'lucide-react'

interface VoiceToastItem {
  id: string
  message: string
  type: 'success' | 'info' | 'confirm'
}

export function VoiceToastContainer() {
  const [toasts, setToasts] = useState<VoiceToastItem[]>([])

  useEffect(() => {
    function handleVoiceToast(e: Event) {
      const detail = (e as CustomEvent).detail as {
        message: string
        type?: 'success' | 'info' | 'confirm'
      }

      const id = `voice-${Date.now()}`
      const toast: VoiceToastItem = {
        id,
        message: detail.message,
        type: detail.type ?? 'info',
      }

      setToasts((prev) => [...prev, toast])

      // Auto-dismiss after 3 seconds
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 3_000)
    }

    window.addEventListener('sophia:voice-toast', handleVoiceToast)
    return () =>
      window.removeEventListener('sophia:voice-toast', handleVoiceToast)
  }, [])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const borderColor = {
    success: 'border-l-sage-500',
    info: 'border-l-blue-500',
    confirm: 'border-l-amber-500',
  }

  return (
    <div className="fixed bottom-20 right-4 z-50 flex flex-col gap-2 max-w-sm">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            transition={{ duration: 0.2 }}
            className={`rounded-lg border border-midnight-700 bg-midnight-800 border-l-[3px] ${borderColor[toast.type]} p-3 shadow-lg`}
            role="status"
            aria-live="polite"
          >
            <div className="flex items-start gap-2">
              <Mic className="h-4 w-4 text-sage-400 flex-none mt-0.5" />
              <p className="flex-1 text-xs text-text-secondary">
                {toast.message}
              </p>
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

/**
 * Dispatch a voice toast event.
 *
 * Call this from voice command handlers to show visual feedback.
 */
export function showVoiceToast(
  message: string,
  type: 'success' | 'info' | 'confirm' = 'info',
) {
  window.dispatchEvent(
    new CustomEvent('sophia:voice-toast', { detail: { message, type } }),
  )
}
