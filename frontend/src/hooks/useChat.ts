/**
 * React hook connecting chat UI to backend SSE endpoint.
 *
 * Manages conversation state, sends messages via POST to /api/orchestrator/chat,
 * parses SSE streaming response, and loads history on mount.
 */

import { useState, useEffect, useCallback } from 'react'
import type { ChatMessage } from '@/components/chat/ChatMessageArea'

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isThinking, setIsThinking] = useState(false)
  const [clientContextId, setClientContextId] = useState<number | null>(null)

  // Load history on mount
  useEffect(() => {
    loadHistory()
  }, [])

  async function loadHistory() {
    try {
      const res = await fetch('/api/orchestrator/chat/history?limit=50')
      if (res.ok) {
        const data = await res.json()
        setMessages(
          data.map((m: { id: number; role: string; content: string; created_at: string }) => ({
            id: String(m.id),
            role: m.role as 'user' | 'sophia',
            content: m.content,
            timestamp: new Date(m.created_at),
          })),
        )
      }
    } catch {
      // History load failure is non-critical -- start with empty chat
    }
  }

  const sendMessage = useCallback(
    async (text: string) => {
      // Add user message immediately (optimistic)
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, userMsg])
      setIsThinking(true)

      try {
        const res = await fetch('/api/orchestrator/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: text,
            client_context_id: clientContextId,
          }),
        })

        // Read SSE stream
        const reader = res.body?.getReader()
        const decoder = new TextDecoder()
        let sophiaContent = ''
        const sophiaMsgId = `sophia-${Date.now()}`

        if (reader) {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const chunk = decoder.decode(value, { stream: true })
            // Parse SSE events (may contain multiple events separated by double newlines)
            const lines = chunk.split('\n')
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const raw = line.slice(6).trim()
                if (!raw) continue
                try {
                  const data = JSON.parse(raw)
                  if (data.type === 'text') {
                    sophiaContent += data.content
                    // Update or add sophia message (streaming)
                    setMessages((prev) => {
                      const existing = prev.find((m) => m.id === sophiaMsgId)
                      if (existing) {
                        return prev.map((m) =>
                          m.id === sophiaMsgId
                            ? { ...m, content: sophiaContent }
                            : m,
                        )
                      }
                      return [
                        ...prev,
                        {
                          id: sophiaMsgId,
                          role: 'sophia' as const,
                          content: sophiaContent,
                          timestamp: new Date(),
                        },
                      ]
                    })
                  } else if (data.type === 'context') {
                    setClientContextId(data.client_id)
                  }
                } catch {
                  // Skip malformed SSE data lines
                }
              }
            }
          }
        }
      } catch {
        // Add error message
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'sophia',
            content: 'Sorry, I had trouble processing that. Please try again.',
            timestamp: new Date(),
          },
        ])
      } finally {
        setIsThinking(false)
      }
    },
    [clientContextId],
  )

  return { messages, isThinking, sendMessage, clientContextId, setClientContextId }
}
