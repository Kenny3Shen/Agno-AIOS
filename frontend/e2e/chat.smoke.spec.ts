import http from 'node:http'
import type { AddressInfo } from 'node:net'
import { expect, test, type Locator, type Page, type Route } from '@playwright/test'
import { openAuthed } from './fixtures'

async function fulfillJson(route: Route, body: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function expectNoActiveHorizontalOffset(page: Page, button: Locator) {
  await expect(button).toBeVisible()
  const idle = await button.boundingBox()
  expect(idle).not.toBeNull()
  if (!idle) return

  await button.hover()
  // Let the button's interaction transition settle before comparing geometry.
  await page.waitForTimeout(250)
  const hovered = await button.boundingBox()
  expect(hovered).not.toBeNull()
  if (!hovered) return
  expect(Math.abs(hovered.x - idle.x)).toBeLessThan(1)
  expect(Math.abs(hovered.width - idle.width)).toBeLessThan(1)

  await page.mouse.move(hovered.x + hovered.width / 2, hovered.y + hovered.height / 2)
  await page.mouse.down()
  try {
    // The press animation completes quickly; inspect after it settles rather than
    // immediately, when a transform transition could still be at its origin.
    await page.waitForTimeout(250)
    const during = await button.boundingBox()
    expect(during).not.toBeNull()
    expect(Math.abs((during?.x ?? Number.NaN) - hovered.x)).toBeLessThan(1)
    expect(Math.abs((during?.width ?? Number.NaN) - hovered.width)).toBeLessThan(1)
    const transform = await button.evaluate(
      (element) => new DOMMatrix(getComputedStyle(element).transform),
    )
    expect(Math.abs(transform.m11 - 1)).toBeLessThan(0.01)
    expect(Math.abs(transform.m41)).toBeLessThan(1)
  } finally {
    // Finish the press away from the control so this visual regression test does
    // not open the model menu or native file picker.
    await page.mouse.move(0, 0)
    await page.mouse.up()
  }
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
  test('model and attachment controls stay stationary while pressed', async ({ page }) => {
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
        return false
      },
    })

    await page.goto('/#/chat', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.chat-page, main').first()).toBeVisible({ timeout: 15_000 })

    await expectNoActiveHorizontalOffset(page, page.getByRole('button', { name: '附件' }))
    await expectNoActiveHorizontalOffset(page, page.getByRole('button', { name: '模型与推理强度' }))
  })

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

      const input = page.getByPlaceholder(/描述你要调查的问题|Describe your/i)
      await expect(input).toBeVisible()
      await input.fill('e2e cancel please')
      await expect(input).toHaveValue('e2e cancel please')

      const send = page.getByRole('button', { name: '发送消息' })
      await expect(send).toBeEnabled()
      await send.click()

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

      const input = page.getByPlaceholder(/描述你要调查的问题|Describe your/i)
      await expect(input).toBeVisible()
      await input.fill('e2e retry then esc')
      await expect(input).toHaveValue('e2e retry then esc')
      const send = page.getByRole('button', { name: '发送消息' })
      await expect(send).toBeEnabled()
      await send.click()

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
