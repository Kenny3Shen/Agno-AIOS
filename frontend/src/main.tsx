import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'virtual:uno.css'
import '@/app/styles/global.css'
import '@/shared/i18n'
import { App } from '@/app/App'
import { AppProviders } from '@/app/providers/AppProviders'

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </StrictMode>
)
