import { asRecord } from '@/shared/lib/format'

/** Agno-style list pagination meta (workbench envelope). */
export type ListPaginationMeta = {
  page: number
  limit: number
  total_count: number
  total_pages: number
  search_time_ms: number
  truncated?: boolean
  scanned_count?: number
  /** Notifications list only. */
  unread_count?: number
}

export type PaginatedList<T, M extends ListPaginationMeta = ListPaginationMeta> = {
  data: T[]
  meta: M
}

type NormalizeListOptions<T> = {
  /** Fallback page when meta.page is absent. */
  page?: number
  /** Fallback limit when meta.limit is absent. */
  limit?: number
  /**
   * Copy optional server meta fields when present:
   * truncated, scanned_count, unread_count.
   */
  extras?: boolean
  mapItem: (row: unknown) => T | null
}

/**
 * Normalize Agno-style ``{ data, meta }`` list payloads.
 * Drops unmapped rows; derives total_pages when the server omits it.
 */
export function normalizePaginatedList<T>(
  payload: unknown,
  options: NormalizeListOptions<T>,
): PaginatedList<T> {
  const envelope = asRecord(payload)
  const meta = asRecord(envelope.meta)
  const rows = Array.isArray(envelope.data) ? envelope.data : []
  const data = rows.map((row) => options.mapItem(row)).filter((row): row is T => row != null)

  const page = Number(meta.page ?? options.page ?? 1) || 1
  const limit = Number(meta.limit ?? options.limit ?? 20) || 20
  const totalCount = Number(meta.total_count ?? data.length) || 0
  const totalPages =
    Number(meta.total_pages ?? (totalCount ? Math.ceil(totalCount / Math.max(limit, 1)) : 0)) || 0

  const base: ListPaginationMeta = {
    page,
    limit,
    total_count: totalCount,
    total_pages: totalPages,
    search_time_ms: Number(meta.search_time_ms ?? 0) || 0,
  }

  if (options.extras) {
    if (meta.truncated != null) base.truncated = Boolean(meta.truncated)
    if (meta.scanned_count != null) base.scanned_count = Number(meta.scanned_count) || 0
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
