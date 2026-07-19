import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { App, theme } from 'antd'
import { ConfigProvider } from 'antd'

const testTheme = {
  algorithm: theme.defaultAlgorithm,
  token: {
    motion: false,
  },
  hashed: false,
} as const

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })

export const renderWithQuery = (ui: ReactElement) => {
  const client = createTestQueryClient()
  return render(
    <QueryClientProvider client={client}>
      <ConfigProvider theme={testTheme}>
        <App>{ui}</App>
      </ConfigProvider>
    </QueryClientProvider>
  )
}
