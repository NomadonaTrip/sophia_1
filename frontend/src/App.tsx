import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router'

import { Layout } from '@/routes/layout'
import { MorningBrief } from '@/routes/morning-brief'
import { ApprovalQueue } from '@/routes/approval-queue'
import { ClientDrillDown } from '@/routes/client'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 3,
      retryDelay: (attempt: number) => Math.min(2000 * 2 ** attempt, 8000),
    },
    mutations: {
      retry: 3,
      retryDelay: (attempt: number) => Math.min(2000 * 2 ** attempt, 8000),
    },
  },
})

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <MorningBrief /> },
      { path: 'morning-brief', element: <MorningBrief /> },
      {
        path: 'client-drill-down',
        element: <ClientDrillDown />,
      },
      {
        path: 'approval-queue',
        element: <ApprovalQueue />,
      },
      {
        path: 'calibration',
        element: <PlaceholderRoute title="Calibration" />,
      },
      {
        path: 'analytics',
        element: <PlaceholderRoute title="Analytics" />,
      },
      {
        path: 'session-close',
        element: <PlaceholderRoute title="Session Close" />,
      },
    ],
  },
])

function PlaceholderRoute({ title }: { title: string }) {
  return (
    <div className="flex items-center justify-center py-20">
      <p className="text-text-muted text-lg">{title} coming soon</p>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
