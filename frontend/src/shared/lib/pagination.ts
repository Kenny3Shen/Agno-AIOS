import { asRecord } from '@/shared/lib/format'

/** Agno-style list pagination meta (workbench envelope). */
export type ListPaginationMeta = {
  page: number
  limit: number
  total_count: number
  total_pages: number
  search_time_ms: number
  truncated?: boolean
  /** Notifications list only. */
  unread_count?: number
}

type PaginatedList<T, M extends ListPaginationMeta = ListPaginationMeta> = {
  data: T[]
  meta: M
}

type NormalizeListOptions<T> = {
  /**
   * Copy optional server meta fields when present:
   * truncated, unread_count.
   */
  extras?: boolean
  mapItem: (row: unknown) => T
}

/**
 * Normalize Agno-style ``{ data, meta }`` list payloads.
 * Rejects malformed envelopes instead of guessing pagination from client
 * request parameters or returned row counts. Item parsers must reject invalid
 * rows so list totals and visible rows cannot silently diverge.
 */
export function normalizePaginatedList<T>(
  payload: unknown,
  options: NormalizeListOptions<T>,
): PaginatedList<T> {
  const envelope = asRecord(payload)
  const meta = asRecord(envelope.meta)
  const rows = envelope.data
  const requiredMetaKeys = ['page', 'limit', 'total_count', 'total_pages', 'search_time_ms'] as const
  if (!Array.isArray(rows) || !requiredMetaKeys.every((key) => typeof meta[key] === 'number')) {
    throw new Error('Invalid paginated list response')
  }
  const data = rows.map(options.mapItem)

  const base: ListPaginationMeta = {
    page: meta.page as number,
    limit: meta.limit as number,
    total_count: meta.total_count as number,
    total_pages: meta.total_pages as number,
    search_time_ms: meta.search_time_ms as number,
  }

  if (options.extras) {
    if (meta.truncated != null) base.truncated = Boolean(meta.truncated)
    if (meta.unread_count != null) base.unread_count = Number(meta.unread_count) || 0
  }

  return { data, meta: base }
}

/** Build list meta when the client already has totals (e.g. Approvals upload tab). */
export function listPaginationMeta(
  page: number,
  limit: number,
  totalCount: number,
  searchTimeMs = 0,
): ListPaginationMeta {
  const safePage = Math.max(1, page)
  const safeLimit = Math.max(1, limit)
  const total = Math.max(0, totalCount)
  return {
    page: safePage,
    limit: safeLimit,
    total_count: total,
    total_pages: total ? Math.ceil(total / safeLimit) : 0,
    search_time_ms: searchTimeMs,
  }
}
