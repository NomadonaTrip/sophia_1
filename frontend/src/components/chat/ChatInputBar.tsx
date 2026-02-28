import { useState, useCallback } from 'react'
import { ArrowUp, Mic, Square } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChatInputBarProps {
  onSend: (message: string) => void
  isThinking?: boolean
  thinkingText?: string
  onMicStart?: () => void
  onMicStop?: () => void
  isRecording?: boolean
}

export function ChatInputBar({
  onSend,
  isThinking = false,
  thinkingText,
  onMicStart,
  onMicStop,
  isRecording = false,
}: ChatInputBarProps) {
  const [message, setMessage] = useState('')

  const handleSend = useCallback(() => {
    const trimmed = message.trim()
    if (trimmed) {
      onSend(trimmed)
      setMessage('')
    }
  }, [message, onSend])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const handleMicToggle = useCallback(() => {
    if (isRecording) {
      onMicStop?.()
    } else {
      onMicStart?.()
    }
  }, [isRecording, onMicStart, onMicStop])

  const canSend = message.trim().length > 0

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50">
      {/* Thinking indicator */}
      {isThinking && (
        <div className="flex items-center gap-2 px-4 py-1.5 justify-center">
          <div className="sage-dot-pulse h-2 w-2 rounded-full bg-sage-400" />
          {thinkingText && (
            <span className="text-xs text-text-muted">{thinkingText}</span>
          )}
        </div>
      )}

      {/* Input bar */}
      <div
        className="bg-midnight-800/80 backdrop-blur-xl border-t border-midnight-700"
        role="form"
        aria-label="Message Sophia"
      >
        <div className="mx-auto w-[60%] flex items-center gap-2 px-3 py-2.5">
          {/* Mic button */}
          <button
            type="button"
            onClick={handleMicToggle}
            className={cn(
              'flex-none flex items-center justify-center h-9 w-9 rounded-md transition-colors',
              isRecording
                ? 'bg-sage-500/20 text-sage-300 sage-dot-pulse'
                : 'bg-midnight-700 text-text-muted hover:text-sage-300 hover:bg-midnight-600',
            )}
            aria-label={isRecording ? 'Stop recording' : 'Start recording'}
          >
            {isRecording ? (
              <Square className="h-4 w-4" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </button>

          {/* Text input */}
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Message Sophia..."
            className="flex-1 h-9 rounded-md border border-midnight-600 bg-midnight-900 px-3 text-sm text-text-primary placeholder:text-text-muted focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sage-400"
            aria-label="Type a message"
          />

          {/* Send button */}
          <button
            type="button"
            onClick={handleSend}
            disabled={!canSend}
            className={cn(
              'flex-none flex items-center justify-center h-9 w-9 rounded-md transition-colors',
              canSend
                ? 'bg-sage-500 text-white shadow-[0_0_12px_rgba(74,124,89,0.3)] hover:bg-sage-400 cursor-pointer'
                : 'bg-midnight-700 text-text-muted cursor-not-allowed opacity-50',
            )}
            aria-label="Send message"
          >
            <ArrowUp className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
