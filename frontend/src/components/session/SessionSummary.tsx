import { Check, Clock } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'

interface SessionSummaryProps {
  approved: number
  edited: number
  regenerated: number
  calibrated: number
  sessionTime: string
}

export function SessionSummary({
  approved,
  edited,
  regenerated,
  calibrated,
  sessionTime,
}: SessionSummaryProps) {
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="relative mx-auto max-w-md rounded-[14px] border border-midnight-700 bg-midnight-800 p-6 text-center overflow-hidden"
        role="status"
        aria-live="polite"
      >
        {/* Radial glow from top center */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(ellipse at 50% 0%, rgba(74,124,89,0.12), transparent 60%)',
          }}
        />

        <div className="relative">
          {/* Header with check icon */}
          <div className="flex items-center justify-center gap-2 mb-4">
            <Check className="h-5 w-5 text-sage-400" />
            <h2 className="font-sophia italic text-xl text-sage-300">
              Session Complete
            </h2>
          </div>

          {/* Stats row */}
          <div className="grid grid-cols-5 gap-2 text-center">
            <StatCell label="Approved" value={approved} />
            <StatCell label="Edited" value={edited} />
            <StatCell label="Regen" value={regenerated} />
            <StatCell label="Calibrated" value={calibrated} />
            <div className="flex flex-col items-center gap-1">
              <div className="flex items-center gap-1 text-text-primary font-medium tabular-nums text-lg">
                <Clock className="h-3.5 w-3.5 text-text-muted" />
                <span>{sessionTime}</span>
              </div>
              <span className="text-[10px] text-text-muted uppercase tracking-wide">
                Time
              </span>
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}

function StatCell({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-text-primary font-medium tabular-nums text-lg">
        {value}
      </span>
      <span className="text-[10px] text-text-muted uppercase tracking-wide">
        {label}
      </span>
    </div>
  )
}
