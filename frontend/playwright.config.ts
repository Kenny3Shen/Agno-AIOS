import { defineConfig, devices } from '@playwright/test'

/**
 * Critical-path browser smoke for shell navigation.
 * API traffic is mocked in specs (no live backend).
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  // Rendering the large Ant Design application in one worker per CPU causes
  // local browser smoke to time out before the UI becomes interactive. Keep
  // CI serial and cap local runs at two independent browser contexts.
  workers: process.env.CI ? 1 : 2,
  reporter: process.env.CI ? 'github' : 'list',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
    ...devices['Desktop Chrome'],
  },
  webServer: {
    // Dev server is enough for shell smoke; API is fully mocked in-spec.
    command: 'bunx vite --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
})
