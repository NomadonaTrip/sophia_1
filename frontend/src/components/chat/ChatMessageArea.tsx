import { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'

export interface ChatMessage {
  id: string
  role: 'user' | 'sophia'
  content: string
  timestamp: Date
}

interface ChatMessageAreaProps {
  messages: ChatMessage[]
  isThinking?: boolean
}

export function ChatMessageArea({ messages, isThinking = false }: ChatMessageAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isThinking])

  if (messages.length === 0 && !isThinking) {
    return (
      <div className="min-h-[30vh] flex items-center justify-center">
        <p className="text-text-muted text-sm italic">
          Message Sophia to start a conversation...
        </p>
      </div>
    )
  }

  return (
    <div className="min-h-[30vh] flex flex-col gap-2 py-2">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={cn(
            'max-w-[90%] rounded-[14px] px-3 py-2 text-sm leading-[1.45]',
            msg.role === 'user'
              ? 'ml-auto bg-midnight-700 text-text-primary border border-midnight-600'
              : 'mr-auto bg-midnight-800 text-text-primary border border-midnight-700 border-l-[3px] border-l-sage-500',
          )}
        >
          {msg.role === 'sophia' && (
            <span className="font-sophia italic text-sage-300 text-xs block mb-1">
              Sophia
            </span>
          )}
          <p>{msg.content}</p>
          <span className="text-[10px] text-text-muted mt-1 block">
            {msg.timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
      ))}

      {isThinking && (
        <div className="mr-auto bg-midnight-800 border border-midnight-700 border-l-[3px] border-l-sage-500 rounded-[14px] px-3 py-2">
          <span className="font-sophia italic text-sage-300 text-xs block mb-1">
            Sophia
          </span>
          <div className="flex items-center gap-1.5">
            <div className="sage-dot-pulse h-1.5 w-1.5 rounded-full bg-sage-400" />
            <div
              className="sage-dot-pulse h-1.5 w-1.5 rounded-full bg-sage-400"
              style={{ animationDelay: '0.2s' }}
            />
            <div
              className="sage-dot-pulse h-1.5 w-1.5 rounded-full bg-sage-400"
              style={{ animationDelay: '0.4s' }}
            />
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
