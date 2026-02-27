import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useCallback } from 'react'
import { useNetworkError } from '@/hooks/useNetworkError'

interface SSEEventData {
  draft_id?: number
  client_id?: number
  old_status?: string
  new_status?: string
  hours_stale?: number
  client_name?: string
}

export function useSSE() {
  const queryClient = useQueryClient()
  const { clearError } = useNetworkError()
  const toastTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showStaleContentToast = useCallback((data: SSEEventData) => {
    // Dispatch a custom event that the toast system can listen for
    const event = new CustomEvent('sophia:stale-content', {
      detail: {
        draftId: data.draft_id,
        clientName: data.client_name ?? 'Unknown client',
        hoursStale: data.hours_stale ?? 0,
      },
    })
    window.dispatchEvent(event)
  }, [])

  useEffect(() => {
    const source = new EventSource('/api/events')

    source.addEventListener('approval_changed', (e: MessageEvent) => {
      const data: SSEEventData = JSON.parse(e.data)
      queryClient.invalidateQueries({ queryKey: ['drafts', data.client_id] })
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
      queryClient.invalidateQueries({ queryKey: ['health-strip'] })
      clearError()
    })

    source.addEventListener('publish_complete', (e: MessageEvent) => {
      const data: SSEEventData = JSON.parse(e.data)
      queryClient.invalidateQueries({ queryKey: ['calendar', data.client_id] })
      clearError()
    })

    source.addEventListener('recovery_complete', (e: MessageEvent) => {
      const data: SSEEventData = JSON.parse(e.data)
      queryClient.invalidateQueries({ queryKey: ['drafts', data.client_id] })
      queryClient.invalidateQueries({ queryKey: ['calendar', data.client_id] })
      clearError()
    })

    source.addEventListener('content_stale', (e: MessageEvent) => {
      const data: SSEEventData = JSON.parse(e.data)
      queryClient.invalidateQueries({ queryKey: ['drafts', data.client_id] })
      showStaleContentToast(data)
    })

    source.onerror = () => {
      // EventSource auto-reconnects by W3C spec. No manual reconnect needed.
    }

    return () => {
      source.close()
      if (toastTimeoutRef.current) {
        clearTimeout(toastTimeoutRef.current)
      }
    }
  }, [queryClient, clearError, showStaleContentToast])
}
