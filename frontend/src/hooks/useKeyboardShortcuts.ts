import { useEffect, useCallback, useRef } from 'react'

interface KeyboardShortcutActions {
  onApprove?: () => void
  onEdit?: () => void
  onReject?: () => void
  onNext?: () => void
  onPrev?: () => void
  onEscape?: () => void
}

/**
 * Keyboard shortcuts for approval queue navigation:
 * A = approve focused item
 * E = edit focused item
 * R = reject focused item
 * N = next item (same direction as Tab)
 * Tab / Shift+Tab = navigate between items
 * Escape = collapse expanded panel
 *
 * Only active when no input/textarea is focused.
 */
export function useKeyboardShortcuts(
  actions: KeyboardShortcutActions,
  enabled = true,
) {
  const actionsRef = useRef(actions)
  actionsRef.current = actions

  const isInputFocused = useCallback(() => {
    const active = document.activeElement
    if (!active) return false
    const tag = active.tagName.toLowerCase()
    return (
      tag === 'input' ||
      tag === 'textarea' ||
      tag === 'select' ||
      (active as HTMLElement).isContentEditable
    )
  }, [])

  useEffect(() => {
    if (!enabled) return

    function handleKeyDown(e: KeyboardEvent) {
      // Skip when typing in form fields
      if (isInputFocused()) return

      switch (e.key.toLowerCase()) {
        case 'a':
          e.preventDefault()
          actionsRef.current.onApprove?.()
          break
        case 'e':
          e.preventDefault()
          actionsRef.current.onEdit?.()
          break
        case 'r':
          e.preventDefault()
          actionsRef.current.onReject?.()
          break
        case 'n':
          e.preventDefault()
          actionsRef.current.onNext?.()
          break
        case 'escape':
          e.preventDefault()
          actionsRef.current.onEscape?.()
          break
        case 'tab':
          // Let Tab/Shift+Tab handle focus naturally for items
          // but also trigger next/prev callbacks for state tracking
          if (e.shiftKey) {
            actionsRef.current.onPrev?.()
          } else {
            actionsRef.current.onNext?.()
          }
          break
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [enabled, isInputFocused])
}
