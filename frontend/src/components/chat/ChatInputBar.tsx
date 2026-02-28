import { useState, useCallback, useEffect, useRef } from 'react'
import { ArrowUp, Mic, Square } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useVoiceInput } from '@/hooks/useVoiceInput'
import type { VoiceResult } from '@/hooks/useVoiceInput'
import { parseVoiceCommand } from '@/components/voice/VoiceCommandParser'
import { showVoiceToast } from '@/components/voice/VoiceToast'

interface VoiceCommandCallbacks {
  onApprove?: () => void
  onReject?: (guidance?: string) => void
  onSkip?: () => void
  onNavigate?: (target: string) => void
}

interface ChatInputBarProps {
  onSend: (message: string) => void
  isThinking?: boolean
  thinkingText?: string
  /** Voice command callbacks for approval actions */
  voiceCommands?: VoiceCommandCallbacks
}

export function ChatInputBar({
  onSend,
  isThinking = false,
  thinkingText,
  voiceCommands,
}: ChatInputBarProps) {
  const [message, setMessage] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  // Voice input hook -- handles SpeechRecognition lifecycle
  const handleVoiceResult = useCallback(
    (result: VoiceResult) => {
      const command = parseVoiceCommand(result.transcript)

      switch (command.action) {
        case 'approve':
          voiceCommands?.onApprove?.()
          showVoiceToast('Approved via voice', 'success')
          break

        case 'reject':
          if (command.confirmation) {
            // Destructive action: show confirmation toast, then execute
            showVoiceToast(
              `Reject with: "${command.guidance}"? (click Reject to confirm)`,
              'confirm',
            )
            // Pre-populate rejection guidance for manual confirmation
            voiceCommands?.onReject?.(command.guidance)
          } else {
            // Edit guidance (e.g. "make it shorter") -- treat as rejection with guidance
            voiceCommands?.onReject?.(command.guidance)
            showVoiceToast(
              `Feedback: "${command.guidance}"`,
              'info',
            )
          }
          break

        case 'skip':
          voiceCommands?.onSkip?.()
          showVoiceToast('Skipped via voice', 'info')
          break

        case 'navigate':
          if (command.target) {
            voiceCommands?.onNavigate?.(command.target)
            showVoiceToast(`Navigating to: ${command.target}`, 'info')
          }
          break

        case 'unknown':
        default:
          // Populate text input with transcript for manual review
          setMessage(result.transcript)
          showVoiceToast(`Heard: "${result.transcript}"`, 'info')
          // Focus the input so the user can edit and send
          inputRef.current?.focus()
          break
      }
    },
    [voiceCommands],
  )

  const { isListening, isSupported, startListening, stopListening } =
    useVoiceInput(handleVoiceResult)

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
    if (isListening) {
      stopListening()
    } else {
      startListening()
    }
  }, [isListening, startListening, stopListening])

  // Keyboard hotkey: hold Space when input not focused to activate mic
  useEffect(() => {
    if (!isSupported) return

    function handleGlobalKeyDown(e: KeyboardEvent) {
      // Only activate when no input/textarea is focused
      const active = document.activeElement
      if (active) {
        const tag = active.tagName.toLowerCase()
        if (
          tag === 'input' ||
          tag === 'textarea' ||
          tag === 'select' ||
          (active as HTMLElement).isContentEditable
        ) {
          return
        }
      }

      if (e.code === 'Space' && !e.repeat) {
        e.preventDefault()
        startListening()
      }
    }

    function handleGlobalKeyUp(e: KeyboardEvent) {
      if (e.code === 'Space') {
        stopListening()
      }
    }

    document.addEventListener('keydown', handleGlobalKeyDown)
    document.addEventListener('keyup', handleGlobalKeyUp)
    return () => {
      document.removeEventListener('keydown', handleGlobalKeyDown)
      document.removeEventListener('keyup', handleGlobalKeyUp)
    }
  }, [isSupported, startListening, stopListening])

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
          {/* Mic button -- hidden if browser doesn't support Web Speech API */}
          {isSupported && (
            <button
              type="button"
              onClick={handleMicToggle}
              className={cn(
                'flex-none flex items-center justify-center h-9 w-9 rounded-md transition-colors',
                isListening
                  ? 'bg-sage-500/20 text-sage-300 sage-dot-pulse'
                  : 'bg-midnight-700 text-text-muted hover:text-sage-300 hover:bg-midnight-600',
              )}
              aria-label={isListening ? 'Stop recording' : 'Start recording'}
            >
              {isListening ? (
                <Square className="h-4 w-4" />
              ) : (
                <Mic className="h-4 w-4" />
              )}
            </button>
          )}

          {/* Text input */}
          <input
            ref={inputRef}
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
