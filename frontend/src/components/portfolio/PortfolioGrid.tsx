import { useMemo, useCallback } from 'react'
import { motion } from 'motion/react'
import { ClientTile, ClientTileSkeleton, type ClientData } from '@/components/portfolio/ClientTile'

interface PortfolioGridProps {
  clients: ClientData[]
  selectedClientId?: number
  onClientSelect: (clientId: number) => void
  isLoading?: boolean
}

const STATUS_ORDER: Record<string, number> = {
  attention: 0,
  calibrating: 1,
  cruising: 2,
}

/** Progressive loading delay tiers per status group */
const STATUS_DELAY: Record<string, number> = {
  attention: 0,       // immediate
  calibrating: 0.05,  // 50ms
  cruising: 0.1,      // 100ms stagger base
}

export function PortfolioGrid({
  clients,
  selectedClientId,
  onClientSelect,
  isLoading = false,
}: PortfolioGridProps) {
  // Sort by urgency: attention first, calibrating second, cruising third
  // Within group: sorted by engagement rate ascending (worst first)
  const sorted = useMemo(
    () =>
      [...clients].sort((a, b) => {
        const statusDiff = STATUS_ORDER[a.status] - STATUS_ORDER[b.status]
        if (statusDiff !== 0) return statusDiff
        return a.engagementRate - b.engagementRate
      }),
    [clients],
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const target = e.target as HTMLElement
      const items = Array.from(
        (e.currentTarget as HTMLDivElement).querySelectorAll('[role="button"]'),
      ) as HTMLElement[]
      const currentIndex = items.indexOf(target)

      let nextIndex = -1
      switch (e.key) {
        case 'ArrowRight':
          nextIndex = Math.min(currentIndex + 1, items.length - 1)
          break
        case 'ArrowLeft':
          nextIndex = Math.max(currentIndex - 1, 0)
          break
        case 'ArrowDown': {
          // Move down by approximate column count based on grid
          const cols = getComputedStyle(e.currentTarget).gridTemplateColumns.split(' ').length
          nextIndex = Math.min(currentIndex + cols, items.length - 1)
          break
        }
        case 'ArrowUp': {
          const colsUp = getComputedStyle(e.currentTarget).gridTemplateColumns.split(' ').length
          nextIndex = Math.max(currentIndex - colsUp, 0)
          break
        }
      }

      if (nextIndex >= 0 && nextIndex !== currentIndex) {
        e.preventDefault()
        items[nextIndex]?.focus()
      }
    },
    [],
  )

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2" role="grid">
        {Array.from({ length: 8 }).map((_, i) => (
          <ClientTileSkeleton key={i} />
        ))}
      </div>
    )
  }

  if (sorted.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-text-muted text-sm">No clients yet</p>
      </div>
    )
  }

  return (
    <motion.div
      className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2"
      role="grid"
      aria-live="polite"
      onKeyDown={handleKeyDown}
      initial="hidden"
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.05 } },
      }}
    >
      {sorted.map((client, index) => {
        const delay = STATUS_DELAY[client.status] + index * 0.02

        return (
          <motion.div
            key={client.id}
            variants={{
              hidden: { opacity: 0, y: 8 },
              visible: { opacity: 1, y: 0 },
            }}
            transition={{ duration: 0.2, delay }}
          >
            <ClientTile
              client={client}
              isSelected={selectedClientId === client.id}
              onClick={onClientSelect}
            />
          </motion.div>
        )
      })}
    </motion.div>
  )
}
