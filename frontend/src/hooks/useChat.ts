/**
 * React hook connecting chat UI to backend SSE endpoint.
 *
 * Manages conversation state, sends messages via POST to /api/orchestrator/chat,
 * parses SSE streaming response, and loads history on mount.
 */

import { useState, useEffect, useCallback } from 'react'
import type { ChatMessage, FileAttachment } from '@/components/chat/ChatMessageArea'

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isThinking, setIsThinking] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [clientContextId, setClientContextId] = useState<number | null>(null)

  // Load history on mount and when client context changes
  useEffect(() => {
    loadHistory(clientContextId)
  }, [clientContextId])

  async function loadHistory(contextId: number | null) {
    try {
      const params = new URLSearchParams({ limit: '50' })
      if (contextId != null) {
        params.set('client_context_id', String(contextId))
      }
      const res = await fetch(`/api/orchestrator/chat/history?${params}`)
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

  /** Read an SSE stream from a fetch response and accumulate Sophia's reply. */
  async function readStream(res: Response, sophiaMsgId: string) {
    const reader = res.body?.getReader()
    const decoder = new TextDecoder()
    let sophiaContent = ''

    if (reader) {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const raw = line.slice(6).trim()
            if (!raw) continue
            try {
              const data = JSON.parse(raw)
              if (data.type === 'text') {
                sophiaContent += data.content
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

        const sophiaMsgId = `sophia-${Date.now()}`
        await readStream(res, sophiaMsgId)
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

  const sendFileMessage = useCallback(
    async (file: File) => {
      setIsUploading(true)

      try {
        // 1. Upload and parse
        const formData = new FormData()
        formData.append('file', file)

        const uploadRes = await fetch('/api/orchestrator/chat/upload-file', {
          method: 'POST',
          body: formData,
        })

        if (!uploadRes.ok) {
          const err = await uploadRes.json().catch(() => ({ detail: 'Upload failed' }))
          throw new Error(err.detail || 'Upload failed')
        }

        const uploadData = await uploadRes.json()
        const fileType = uploadData.file_type as 'excel' | 'text' | 'image'

        // 2. Build file attachment metadata
        const fileAttachment: FileAttachment = {
          filename: uploadData.filename,
          fileType,
          ...(fileType === 'excel' && {
            sheetNames: uploadData.sheet_names,
            totalRows: uploadData.total_rows,
            truncated: uploadData.truncated,
          }),
          ...(fileType === 'text' && {
            truncated: uploadData.truncated,
          }),
          ...(fileType === 'image' && {
            imageUrl: uploadData.image_url,
          }),
        }

        // 3. Build display content based on type
        let messageText: string
        if (fileType === 'excel') {
          messageText = `Here's a spreadsheet: **${uploadData.filename}**\n\n${uploadData.parsed_text}`
        } else if (fileType === 'text') {
          messageText = `Here's a file: **${uploadData.filename}**\n\n${uploadData.parsed_text}`
        } else {
          messageText = `Shared an image: **${uploadData.filename}**`
        }

        // 4. Add optimistic user message with file chip
        const userMsg: ChatMessage = {
          id: `user-${Date.now()}`,
          role: 'user',
          content: messageText,
          timestamp: new Date(),
          fileAttachment,
        }
        setMessages((prev) => [...prev, userMsg])
        setIsUploading(false)
        setIsThinking(true)

        // 5. Send parsed content as normal chat message
        const chatRes = await fetch('/api/orchestrator/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: messageText,
            client_context_id: clientContextId,
          }),
        })

        const sophiaMsgId = `sophia-${Date.now()}`
        await readStream(chatRes, sophiaMsgId)
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : 'Failed to process file'
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: 'sophia',
            content: `Sorry, I couldn't process that file: ${errorMessage}`,
            timestamp: new Date(),
          },
        ])
      } finally {
        setIsUploading(false)
        setIsThinking(false)
      }
    },
    [clientContextId],
  )

  return {
    messages,
    isThinking,
    isUploading,
    sendMessage,
    sendFileMessage,
    clientContextId,
    setClientContextId,
  }
}
