import { useState, useCallback } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router'
import {
  LayoutGrid,
  User,
  CheckSquare,
  SlidersHorizontal,
  BarChart3,
  LogOut,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { HealthStrip } from '@/components/health/HealthStrip'
import { ChatInputBar } from '@/components/chat/ChatInputBar'
import { ScrollArea } from '@/components/ui/scroll-area'

const NAV_TABS = [
  { label: 'Morning Brief', path: '/morning-brief', icon: LayoutGrid },
  { label: 'Client Drill-Down', path: '/client-drill-down', icon: User },
  { label: 'Approval Queue', path: '/approval-queue', icon: CheckSquare },
  { label: 'Calibration', path: '/calibration', icon: SlidersHorizontal },
  { label: 'Analytics', path: '/analytics', icon: BarChart3 },
  { label: 'Session Close', path: '/session-close', icon: LogOut },
] as const

export function Layout() {
  const navigate = useNavigate()
  const location = useLocation()
  const [isThinking, setIsThinking] = useState(false)

  const currentPath =
    location.pathname === '/' ? '/morning-brief' : location.pathname

  const handleSend = useCallback(
    (_message: string) => {
      setIsThinking(true)
      // Placeholder: simulate thinking then stop
      setTimeout(() => setIsThinking(false), 2000)
    },
    [],
  )

  return (
    <div className="flex min-h-screen flex-col bg-midnight-900">
      {/* Top nav */}
      <header className="sticky top-0 z-40 bg-midnight-900/80 backdrop-blur-sm border-b border-midnight-700">
        <div className="mx-auto max-w-5xl flex items-center gap-2 px-4 py-2.5">
          {/* Logo */}
          <span className="font-sophia italic text-lg text-sage-300 mr-4 flex-none">
            Sophia
          </span>

          {/* Tab nav */}
          <nav className="flex items-center gap-1 overflow-x-auto" role="tablist">
            {NAV_TABS.map((tab) => {
              const isActive = currentPath === tab.path
              const Icon = tab.icon

              return (
                <button
                  key={tab.path}
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => navigate(tab.path)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors whitespace-nowrap cursor-pointer',
                    isActive
                      ? 'bg-midnight-700 text-sage-300'
                      : 'text-text-muted hover:text-text-secondary hover:bg-midnight-800',
                  )}
                >
                  <Icon className="h-3.5 w-3.5 flex-none" />
                  <span className="hidden md:inline">{tab.label}</span>
                </button>
              )
            })}
          </nav>
        </div>
      </header>

      {/* Health strip */}
      <HealthStrip
        cruising={12}
        calibrating={3}
        attention={1}
        postsRemaining={8}
      />

      {/* Main content area */}
      <main className="flex-1 pb-20">
        <ScrollArea className="h-full">
          <div className="mx-auto max-w-[720px] px-4 py-4">
            <AnimatePresence mode="wait">
              <motion.div
                key={currentPath}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </div>
        </ScrollArea>
      </main>

      {/* Fixed bottom chat input */}
      <ChatInputBar onSend={handleSend} isThinking={isThinking} />
    </div>
  )
}
