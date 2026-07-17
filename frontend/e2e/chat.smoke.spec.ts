import http from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test, type Route } from '@playwright/test'
import { openAuthed } from './fixtures'

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

/**
 * Offline hanging SSE: Playwright fulfill only accepts a finished body, so we
 * continue the chat POST to a local server that writes run.started + delta and
 * stays open until the client aborts (stop button).
 */
async function startHangingChatSseServer() {
  const server = http.createServer((req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Authorization, Content-Type, Accept',
      })
      res.end()
      return
    }

    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    })
    res.write('event: run.started\ndata: {"run_id":"run-e2e-1","session_id":"sess-e2e-1"}\n\n')
    res.write('event: content.delta\ndata: {"run_id":"run-e2e-1","delta":"partial answer"}\n\n')

    const keepAlive = setInterval(() => {
      try {
        res.write(': keepalive\n\n')
      } catch {
        clearInterval(keepAlive)
      }
    }, 500)

    // Only tear down on response close (client abort). req 'close' after POST body
    // would end the hang stream too early.
    const cleanup = () => {
      clearInterval(keepAlive)
      try {
        res.end()
      } catch {
        // already closed
      }
    }
    res.on('close', cleanup)
  })

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => resolve())
  })
  const { port } = server.address() as AddressInfo
  return {
    url: `http://127.0.0.1:${port}/chat-sse`,
    close: () =>
      new Promise<void>((resolve, reject) => {
        server.close((error) => (error ? reject(error) : resolve()))
      }),
  }
}


/**
 * SSE that emits run.started + run.retrying, then hangs (model backoff UI).
 */
async function startRetryingChatSseServer() {
  const server = http.createServer((req, res) => {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Authorization, Content-Type, Accept',
      })
      res.end()
      return
    }

    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    })
    res.write('event: run.started\ndata: {"run_id":"run-e2e-retry","session_id":"sess-e2e-retry"}\n\n')
    res.write(
      'event: run.retrying\ndata: {"run_id":"run-e2e-retry","attempt":1,"max_attempts":4,"delay_seconds":30,"message":"503"}\n\n',
    )

    const keepAlive = setInterval(() => {
      try {
        res.write(': keepalive\n\n')
      } catch {
        clearInterval(keepAlive)
      }
    }, 500)

    const cleanup = () => {
      clearInterval(keepAlive)
      try {
        res.end()
      } catch {
        // already closed
      }
    }
    res.on('close', cleanup)
  })

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => resolve())
  })
  const { port } = server.address() as AddressInfo
  return {
    url: `http://127.0.0.1:${port}/chat-sse-retry`,
    close: () =>
      new Promise<void>((resolve, reject) => {
        server.close((error) => (error ? reject(error) : resolve()))
      }),
  }
}

test.describe('chat critical path', () => {
  test('stop button cancels active run', async ({ page }) => {
    const sse = await startHangingChatSseServer()
    let cancelCalls = 0

    try {
      await openAuthed(page, '/dashboard', {
        handleApi: async ({ method, path, route }) => {
          if (method === 'GET' && path.endsWith('/api/models')) {
            await fulfillJson(route, {
              active_model_id: 'model-1',
              models: [
                {
                  id: 'model-1',
                  name: 'E2E Model',
                  provider: 'openai',
                  model_id: 'gpt-test',
                  base_url: '',
                  api_key: 'sk-test',
                  api_protocol: 'chat-completions',
                  structured_output_mode: 'native',
                  description: '',
                  enabled: true,
                  builtin: false,
                  configured: true,
                },
              ],
            })
            return true
          }
          if (method === 'GET' && path.endsWith('/api/settings/chat')) {
            await fulfillJson(route, {
              enable_user_memories: false,
              add_history_to_context: true,
              num_history_runs: 3,
            })
            return true
          }
          if (method === 'POST' && path.endsWith('/api/chat')) {
            await route.continue({ url: sse.url })
            return true
          }
          if (method === 'POST' && path.endsWith('/api/chat/runs/run-e2e-1/cancel')) {
            cancelCalls += 1
            await fulfillJson(route, { success: true })
            return true
          }
          return false
        },
      })

      await page.goto('/#/chat', { waitUntil: 'domcontentloaded' })
      await expect(page.locator('.chat-page, main').first()).toBeVisible({ timeout: 15_000 })

      const input = page.locator('textarea').first()
      await expect(input).toBeVisible()
      await input.fill('e2e cancel please')

      await page.getByRole('button', { name: '发送消息' }).click()

      const stop = page.getByRole('button', { name: '停止生成' })
      await expect(stop).toBeVisible({ timeout: 10_000 })
      await stop.click()

      await expect.poll(() => cancelCalls, { timeout: 10_000 }).toBe(1)
    } finally {
      await sse.close().catch(() => undefined)
    }
  })

  test('Esc cancels while model is retrying', async ({ page }) => {
    const sse = await startRetryingChatSseServer()
    let cancelCalls = 0

    try {
      await openAuthed(page, '/dashboard', {
        handleApi: async ({ method, path, route }) => {
          if (method === 'GET' && path.endsWith('/api/models')) {
            await fulfillJson(route, {
              active_model_id: 'model-1',
              models: [
                {
                  id: 'model-1',
                  name: 'E2E Model',
                  provider: 'openai',
                  model_id: 'gpt-test',
                  base_url: '',
                  api_key: 'sk-test',
                  api_protocol: 'chat-completions',
                  structured_output_mode: 'native',
                  description: '',
                  enabled: true,
                  builtin: false,
                  configured: true,
                },
              ],
            })
            return true
          }
          if (method === 'GET' && path.endsWith('/api/settings/chat')) {
            await fulfillJson(route, {
              enable_user_memories: false,
              add_history_to_context: true,
              num_history_runs: 3,
            })
            return true
          }
          if (method === 'POST' && path.endsWith('/api/chat')) {
            await route.continue({ url: sse.url })
            return true
          }
          if (method === 'POST' && path.endsWith('/api/chat/runs/run-e2e-retry/cancel')) {
            cancelCalls += 1
            await fulfillJson(route, { success: true })
            return true
          }
          return false
        },
      })

      await page.goto('/#/chat', { waitUntil: 'domcontentloaded' })
      await expect(page.locator('.chat-page, main').first()).toBeVisible({ timeout: 15_000 })

      const input = page.locator('textarea').first()
      await expect(input).toBeVisible()
      await input.fill('e2e retry then esc')
      await page.getByRole('button', { name: '发送消息' }).click()

      // Retry banner while backoff is in progress; Stop is the sender FAB (Esc).
      await expect(page.getByText(/重试|retry/i).first()).toBeVisible({ timeout: 10_000 })
      await expect(page.getByLabel('停止生成')).toBeVisible()

      // Esc stops even during model-layer retry (not only first stream).
      await page.keyboard.press('Escape')
      await expect.poll(() => cancelCalls, { timeout: 10_000 }).toBe(1)
    } finally {
      await sse.close().catch(() => undefined)
    }
  })


})
