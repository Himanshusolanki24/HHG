import { StrictMode, lazy, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TooltipProvider } from '@radix-ui/react-tooltip'
import { MotionConfig } from 'motion/react'
import './index.css'
import App from './App.tsx'

const KitchenSink = lazy(() => import('./KitchenSink.tsx'))
const qc = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } } })
// ponytail: two routes don't need a router; add one if a third appears.
const page = location.pathname.startsWith('/kitchen-sink') ? <Suspense><KitchenSink /></Suspense> : <App />

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <TooltipProvider delayDuration={250}>
        <MotionConfig reducedMotion="user">{page}</MotionConfig>
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
)
