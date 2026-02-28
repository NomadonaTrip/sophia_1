/**
 * Voice command parser for approval actions.
 *
 * Maps speech transcripts to approval actions. Destructive actions
 * (reject, recovery) require visual confirmation before executing.
 * Approvals and regeneration execute immediately on voice.
 */

export interface VoiceCommand {
  action: 'approve' | 'reject' | 'edit' | 'skip' | 'navigate' | 'unknown'
  /** Rejection/edit guidance text (e.g. "too formal") */
  guidance?: string
  /** Navigation target (client name or keyword) */
  target?: string
  /** Whether this command requires visual confirmation before executing */
  confirmation?: boolean
}

/**
 * Parse a speech transcript into a structured VoiceCommand.
 *
 * Patterns are matched case-insensitively. The first matching pattern
 * wins. Unknown transcripts return action='unknown' so the ChatInputBar
 * can populate the text input for manual review.
 */
export function parseVoiceCommand(transcript: string): VoiceCommand {
  const lower = transcript.toLowerCase().trim()

  // Approve patterns -- execute immediately
  if (
    /^(approve|approve this|yes|looks good|good to go|approve it|ship it|send it|post it|publish)/.test(
      lower,
    )
  ) {
    return { action: 'approve' }
  }

  // Explicit reject patterns -- require confirmation
  if (
    /^(reject|no|not this one|too formal|too casual|wrong angle|off-brand|too long|too short|try again)/.test(
      lower,
    )
  ) {
    return { action: 'reject', guidance: lower, confirmation: true }
  }

  // Edit/guidance patterns -- treated as rejection with guidance
  if (
    /^(make it|change|shorter|longer|more|less|funnier|serious|rewrite|rephrase)/.test(
      lower,
    )
  ) {
    return { action: 'reject', guidance: lower }
  }

  // Skip patterns
  if (/^(skip|skip this|next|pass|move on)/.test(lower)) {
    return { action: 'skip' }
  }

  // Navigation patterns
  if (/^(show me|go to|switch to|let's talk about)/.test(lower)) {
    const target = lower
      .replace(/^(show me|go to|switch to|let's talk about)\s*/, '')
      .trim()
    return { action: 'navigate', target }
  }

  return { action: 'unknown' }
}
