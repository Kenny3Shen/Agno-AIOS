import { ref, computed } from 'vue'

export function usePagination(initialPage: number = 1, initialPageSize: number = 10) {
  const currentPage = ref(initialPage)
  const pageSize = ref(initialPageSize)
  const total = ref(0)

  const totalPages = computed(() => Math.ceil(total.value / pageSize.value))

  const reset = () => {
    currentPage.value = initialPage
  }

  const setPage = (page: number) => {
    if (page >= 1 && page <= totalPages.value) {
      currentPage.value = page
    }
  }

  const setPageSize = (size: number) => {
    pageSize.value = size
    currentPage.value = 1
  }

  const setTotal = (count: number) => {
    total.value = count
  }

  return {
    currentPage,
    pageSize,
    total,
    totalPages,
    reset,
    setPage,
    setPageSize,
    setTotal
  }
}
