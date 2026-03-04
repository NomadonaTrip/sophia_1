import { useEffect, useRef } from 'react'
import { FileSpreadsheet, FileText, ImageIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface FileAttachment {
  filename: string
  fileType: 'excel' | 'text' | 'image'
  /** Excel-specific */
  sheetNames?: string[]
  totalRows?: number
  truncated?: boolean
  /** Image-specific */
  imageUrl?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'sophia'
  content: string
  timestamp: Date
  fileAttachment?: FileAttachment
}

interface ChatMessageAreaProps {
  messages: ChatMessage[]
  isThinking?: boolean
}

function FileChip({ attachment }: { attachment: FileAttachment }) {
  const Icon =
    attachment.fileType === 'excel'
      ? FileSpreadsheet
      : attachment.fileType === 'text'
        ? FileText
        : ImageIcon

  return (
    <div className="flex items-center gap-1.5 mb-1.5 px-2 py-1 rounded-md bg-midnight-600/50 border border-midnight-500/50 w-fit">
      <Icon className="h-3.5 w-3.5 text-sage-400 flex-none" />
      <span className="text-xs text-sage-300 font-medium truncate max-w-[200px]">
        {attachment.filename}
      </span>
      {attachment.fileType === 'excel' && attachment.totalRows != null && (
        <span className="text-[10px] text-text-muted">
          {attachment.totalRows} rows
          {attachment.truncated && ' (truncated)'}
        </span>
      )}
      {attachment.fileType === 'text' && attachment.truncated && (
        <span className="text-[10px] text-text-muted">(truncated)</span>
      )}
    </div>
  )
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
          {msg.fileAttachment && (
            <>
              <FileChip attachment={msg.fileAttachment} />
              {msg.fileAttachment.fileType === 'image' && msg.fileAttachment.imageUrl && (
                <img
                  src={msg.fileAttachment.imageUrl}
                  alt={msg.fileAttachment.filename}
                  className="max-w-[280px] max-h-[200px] rounded-md mb-1.5 object-contain"
                />
              )}
            </>
          )}
          <p>
            {msg.content}
            {/* Blinking cursor for streaming sophia messages */}
            {isThinking && msg.role === 'sophia' && msg.id === messages[messages.length - 1]?.id && (
              <span className="inline-block w-[2px] h-[14px] bg-sage-400 ml-0.5 align-text-bottom animate-pulse" />
            )}
          </p>
          <span className="text-[10px] text-text-muted mt-1 block">
            {msg.timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        </div>
      ))}

      {/* Show dot-pulse thinking indicator only when no streaming content is being displayed */}
      {isThinking && (messages.length === 0 || messages[messages.length - 1]?.role !== 'sophia') && (
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
