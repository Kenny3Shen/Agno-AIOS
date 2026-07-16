import { describe, expect, it } from 'vitest'
import { listPaginationMeta, normalizePaginatedList } from './pagination'

describe('normalizePaginatedList', () => {
  it('maps data rows and derives total_pages', () => {
    const result = normalizePaginatedList(
      {
        data: [{ id: 'a' }, { id: '' }, { id: 'b' }],
        meta: { page: 2, limit: 10, total_count: 25, search_time_ms: 3 },
      },
      {
        mapItem: (row) => {
          const id = String((row as { id?: string }).id ?? '').trim()
          return id ? { id } : null
        },
      },
    )
    expect(result.data).toEqual([{ id: 'a' }, { id: 'b' }])
    expect(result.meta).toMatchObject({
      page: 2,
      limit: 10,
      total_count: 25,
      total_pages: 3,
      search_time_ms: 3,
    })
  })

  it('preserves truncated extras when requested', () => {
    const result = normalizePaginatedList(
      {
        data: [],
        meta: { page: 1, limit: 20, total_count: 0, truncated: true, scanned_count: 40, unread_count: 2 },
      },
      { mapItem: () => null, extras: true },
    )
    expect(result.meta.truncated).toBe(true)
    expect(result.meta.scanned_count).toBe(40)
    expect(result.meta.unread_count).toBe(2)
  })
})

describe('listPaginationMeta', () => {
  it('clamps and computes total_pages', () => {
    expect(listPaginationMeta(1, 20, 45)).toEqual({
      page: 1,
      limit: 20,
      total_count: 45,
      total_pages: 3,
      search_time_ms: 0,
    })
  })
})
