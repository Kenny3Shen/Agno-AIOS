import { afterEach, describe, expect, it, vi } from 'vitest'

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' },
    status: 200,
  })
}

describe('workspace API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('passes trace date range filters to the backend query string', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: 'ok' }))
      .mockResolvedValueOnce(
        jsonResponse({
          items: [],
          total_count: 0,
          page: 1,
          limit: 50,
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const { listTraces } = await import('./workspace.ts')

    await listTraces({
      page: 1,
      limit: 50,
      status: 'OK',
      start_time: '2026-06-01T00:00:00.000Z',
      end_time: '2026-06-29T23:59:59.000Z',
    })

    const [url] = fetchMock.mock.calls[1]
    const parsedUrl = new URL(String(url), 'http://localhost')
    expect(parsedUrl.pathname).toBe('/api/traces')
    expect(parsedUrl.searchParams.get('status')).toBe('OK')
    expect(parsedUrl.searchParams.get('start_time')).toBe(
      '2026-06-01T00:00:00.000Z',
    )
    expect(parsedUrl.searchParams.get('end_time')).toBe(
      '2026-06-29T23:59:59.000Z',
    )
  })
})
