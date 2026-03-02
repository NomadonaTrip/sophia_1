import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router'
import {
  LayoutGrid,
  User,
  CheckSquare,
  SlidersHorizontal,
  BarChart3,
  LogOut,
  ChevronUp,
  ChevronDown,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { cn } from '@/lib/utils'
import { HealthStrip } from '@/components/health/HealthStrip'
import { ChatInputBar } from '@/components/chat/ChatInputBar'
import { ChatMessageArea } from '@/components/chat/ChatMessageArea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { NetworkErrorBanner } from '@/components/approval/NetworkErrorBanner'
import { StaleContentToastContainer } from '@/components/approval/StaleContentToast'
import { VoiceToastContainer } from '@/components/voice/VoiceToast'
import { useSSE } from '@/hooks/useSSE'
import { useChat } from '@/hooks/useChat'

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
  const [panelCollapsed, setPanelCollapsed] = useState(false)

  // Real chat hook -- replaces hardcoded responses with backend SSE streaming
  const { messages, isThinking, sendMessage } = useChat()

  // Activate SSE connection for real-time sync
  useSSE()

  const currentPath =
    location.pathname === '/' ? '/morning-brief' : location.pathname

  return (
    <div className="flex min-h-screen flex-col bg-midnight-900">
      {/* Top nav */}
      <header className="sticky top-0 z-40 bg-midnight-900/80 backdrop-blur-sm border-b border-midnight-700">
        <div className="mx-auto w-[60%] flex items-center gap-2 px-4 py-2.5">
          {/* Logo */}
          <span className="font-sophia italic text-lg text-sage-300 mr-4 flex-none">
            Sophia
          </span>

          {/* Tab nav */}
          <nav className="flex flex-1 items-center justify-between overflow-x-auto" role="tablist">
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

      {/* Network error banner */}
      <NetworkErrorBanner />

      {/* Stale content toast overlay */}
      <StaleContentToastContainer />

      {/* Voice command feedback toast */}
      <VoiceToastContainer />

      {/* Health strip */}
      <HealthStrip
        cruising={12}
        calibrating={3}
        attention={1}
        postsRemaining={8}
      />

      {/* Main content: collapsible route content (top) + conversation (bottom) */}
      <main className="flex-1 flex flex-col pb-16 overflow-hidden">
        {/* Route content panel — collapsible */}
        {!panelCollapsed && (
          <ScrollArea className="flex-1 min-h-0">
            <div className="mx-auto w-[60%] px-4 py-4">
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
        )}

        {/* Collapse/expand toggle bar */}
        <button
          type="button"
          onClick={() => setPanelCollapsed((p) => !p)}
          className="flex items-center justify-center gap-1.5 py-1 border-t border-midnight-700 bg-midnight-800/60 hover:bg-midnight-700/60 text-text-muted hover:text-text-secondary transition-colors cursor-pointer flex-none"
          aria-label={panelCollapsed ? 'Show cards' : 'Hide cards'}
        >
          {panelCollapsed ? (
            <>
              <ChevronDown className="h-3.5 w-3.5" />
              <span className="text-[11px]">Show {NAV_TABS.find((t) => t.path === currentPath)?.label ?? 'cards'}</span>
            </>
          ) : (
            <>
              <ChevronUp className="h-3.5 w-3.5" />
              <span className="text-[11px]">Focus chat</span>
            </>
          )}
        </button>

        {/* Conversation area — expands when panel collapsed, 30vh min otherwise */}
        <div
          className={cn(
            'border-t border-midnight-700 overflow-y-auto',
            panelCollapsed ? 'flex-1' : 'h-[30vh] min-h-[30vh]',
          )}
        >
          <div className="mx-auto w-[60%] px-4">
            <ChatMessageArea messages={messages} isThinking={isThinking} />
          </div>
        </div>
      </main>

      {/* Fixed bottom chat input */}
      <ChatInputBar onSend={sendMessage} isThinking={isThinking} />
    </div>
  )
}
