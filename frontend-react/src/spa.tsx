import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { SecurityPlatform } from '#/components/security-platform.tsx'

import './styles.css'

const rootElement = document.getElementById('app')

if (!rootElement) {
  throw new Error('Missing #app root element.')
}

const queryClient = new QueryClient()

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SecurityPlatform />
    </QueryClientProvider>
  </StrictMode>,
)
