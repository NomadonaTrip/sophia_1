/**
 * Web Speech API hook with push-to-talk activation.
 *
 * Uses SpeechRecognition (Chrome/Edge only). Feature-detects browser
 * support and exposes `isSupported` so the mic button can be hidden
 * in unsupported browsers (Firefox, Safari).
 *
 * Push-to-talk: continuous=false, interimResults=false.
 * Visual feedback only -- no TTS responses.
 */

import { useState, useCallback, useRef, useEffect } from 'react'

export interface VoiceResult {
  transcript: string
  confidence: number
}

// ---------------------------------------------------------------------------
// Web Speech API type shims (not in default TS lib)
// ---------------------------------------------------------------------------
interface SpeechRecognitionAlternative {
  readonly transcript: string
  readonly confidence: number
}

interface SpeechRecognitionResult {
  readonly length: number
  item(index: number): SpeechRecognitionAlternative
  readonly [index: number]: SpeechRecognitionAlternative
}

interface SpeechRecognitionResultList {
  readonly length: number
  item(index: number): SpeechRecognitionResult
  readonly [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionEvent extends Event {
  readonly results: SpeechRecognitionResultList
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start(): void
  stop(): void
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionInstance
}

// Extend Window for vendor-prefixed SpeechRecognition
declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
}

export function useVoiceInput(onResult: (result: VoiceResult) => void) {
  const [isListening, setIsListening] = useState(false)
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)
  const onResultRef = useRef(onResult)

  // Keep callback ref current to avoid stale closures
  useEffect(() => {
    onResultRef.current = onResult
  }, [onResult])

  // Feature detection: Web Speech API only in Chrome/Edge
  const isSupported =
    typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)

  const startListening = useCallback(() => {
    if (!isSupported) return
    // Prevent double-start
    if (recognitionRef.current) return

    const Ctor = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!Ctor) return

    const recognition = new Ctor()
    recognition.continuous = false // Single utterance per push (push-to-talk)
    recognition.interimResults = false // Final results only
    recognition.lang = 'en-US'

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const alt = event.results[0][0]
      onResultRef.current({
        transcript: alt.transcript,
        confidence: alt.confidence,
      })
    }

    recognition.onend = () => {
      setIsListening(false)
      recognitionRef.current = null
    }

    recognition.onerror = () => {
      setIsListening(false)
      recognitionRef.current = null
    }

    recognitionRef.current = recognition
    recognition.start()
    setIsListening(true)
  }, [isSupported])

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop()
    recognitionRef.current = null
    setIsListening(false)
  }, [])

  return { isListening, isSupported, startListening, stopListening }
}
