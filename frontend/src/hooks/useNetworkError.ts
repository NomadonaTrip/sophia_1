import { useState, useCallback } from 'react'

interface NetworkErrorState {
  hasError: boolean
  retryCount: number
  maxRetries: number
  isRetrying: boolean
  message: string
}

const DEFAULT_STATE: NetworkErrorState = {
  hasError: false,
  retryCount: 0,
  maxRetries: 3,
  isRetrying: false,
  message: '',
}

// Singleton state for network errors (shared across components)
let globalState = { ...DEFAULT_STATE }
let listeners: Array<() => void> = []

function notify() {
  listeners.forEach((l) => l())
}

export function useNetworkError() {
  const [, setTick] = useState(0)

  // Subscribe to global state changes
  const forceUpdate = useCallback(() => setTick((t) => t + 1), [])

  // Register listener on first render
  useState(() => {
    listeners.push(forceUpdate)
    return () => {
      listeners = listeners.filter((l) => l !== forceUpdate)
    }
  })

  const setError = useCallback((message: string) => {
    globalState = {
      ...globalState,
      hasError: true,
      message,
    }
    notify()
  }, [])

  const incrementRetry = useCallback(() => {
    globalState = {
      ...globalState,
      retryCount: globalState.retryCount + 1,
      isRetrying: true,
    }
    notify()
  }, [])

  const clearError = useCallback(() => {
    if (globalState.hasError) {
      globalState = { ...DEFAULT_STATE }
      notify()
    }
  }, [])

  const startRetrying = useCallback(() => {
    globalState = {
      ...globalState,
      isRetrying: true,
      retryCount: 0,
    }
    notify()
  }, [])

  const stopRetrying = useCallback(() => {
    globalState = {
      ...globalState,
      isRetrying: false,
    }
    notify()
  }, [])

  return {
    ...globalState,
    setError,
    incrementRetry,
    clearError,
    startRetrying,
    stopRetrying,
  }
}
