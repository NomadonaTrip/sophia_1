import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useCallback } from 'react'
import { apiFetch } from '@/lib/api'

interface ApprovalActionResponse {
  id: number
  status: string
  message?: string
}

interface ApprovePayload {
  draftId: number
  publishMode?: 'auto' | 'manual'
  customPostTime?: string
}

interface RejectPayload {
  draftId: number
  tags: string[]
  guidance?: string
}

interface EditPayload {
  draftId: number
  copy: string
  customPostTime?: string
}

interface SkipPayload {
  draftId: number
}

interface UploadImagePayload {
  draftId: number
  file: File
}

interface RecoverPayload {
  draftId: number
  reason: string
  urgency: 'immediate' | 'review'
}

export function useApproval() {
  const queryClient = useQueryClient()
  const [rejectionCounts, setRejectionCounts] = useState<Record<number, number>>({})

  const shouldSuggestCalibration = useCallback(
    (clientId: number) => (rejectionCounts[clientId] ?? 0) >= 3,
    [rejectionCounts],
  )

  const approve = useMutation({
    mutationFn: ({ draftId, publishMode, customPostTime }: ApprovePayload) =>
      apiFetch<ApprovalActionResponse>(`/approval/drafts/${draftId}/approve`, {
        method: 'POST',
        body: JSON.stringify({
          publish_mode: publishMode ?? 'auto',
          custom_post_time: customPostTime,
        }),
      }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
      queryClient.invalidateQueries({ queryKey: ['health-strip'] })
      // Optimistic handled at component level via local state
      void variables
    },
  })

  const reject = useMutation({
    mutationFn: ({ draftId, tags, guidance }: RejectPayload) =>
      apiFetch<ApprovalActionResponse>(`/approval/drafts/${draftId}/reject`, {
        method: 'POST',
        body: JSON.stringify({ tags, guidance }),
      }),
    onSuccess: (_data, variables) => {
      // Track rejection count per client for calibration auto-suggest
      const clientId = variables.draftId // In production, map draft -> client
      setRejectionCounts((prev) => ({
        ...prev,
        [clientId]: (prev[clientId] ?? 0) + 1,
      }))
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
      queryClient.invalidateQueries({ queryKey: ['health-strip'] })
    },
  })

  const edit = useMutation({
    mutationFn: ({ draftId, copy, customPostTime }: EditPayload) =>
      apiFetch<ApprovalActionResponse>(`/approval/drafts/${draftId}/edit`, {
        method: 'POST',
        body: JSON.stringify({ copy, custom_post_time: customPostTime }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
    },
  })

  const skip = useMutation({
    mutationFn: ({ draftId }: SkipPayload) =>
      apiFetch<ApprovalActionResponse>(`/approval/drafts/${draftId}/skip`, {
        method: 'POST',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
      queryClient.invalidateQueries({ queryKey: ['health-strip'] })
    },
  })

  const uploadImage = useMutation({
    mutationFn: ({ draftId, file }: UploadImagePayload) => {
      const formData = new FormData()
      formData.append('file', file)
      return fetch(`/api/approval/drafts/${draftId}/upload-image`, {
        method: 'POST',
        body: formData,
      }).then((res) => {
        if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
        return res.json() as Promise<ApprovalActionResponse>
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
    },
  })

  const recover = useMutation({
    mutationFn: ({ draftId, reason, urgency }: RecoverPayload) =>
      apiFetch<ApprovalActionResponse>(`/approval/drafts/${draftId}/recover`, {
        method: 'POST',
        body: JSON.stringify({ reason, urgency }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['drafts'] })
      queryClient.invalidateQueries({ queryKey: ['health-strip'] })
    },
  })

  return {
    approve,
    reject,
    edit,
    skip,
    uploadImage,
    recover,
    rejectionCounts,
    shouldSuggestCalibration,
  }
}
