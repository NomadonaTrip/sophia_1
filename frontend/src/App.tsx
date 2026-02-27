import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router'

import { Layout } from '@/routes/layout'
import { MorningBrief } from '@/routes/morning-brief'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
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
        element: <PlaceholderRoute title="Client Drill-Down" />,
      },
      {
        path: 'approval-queue',
        element: <PlaceholderRoute title="Approval Queue" />,
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
