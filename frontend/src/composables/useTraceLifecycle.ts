import { onMounted, onUnmounted } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"

interface UseTraceLifecycleParams {
  refresh: () => Promise<void>
  clearPendingFilterRefresh: () => void
}

export const useTraceLifecycle = ({
  refresh,
  clearPendingFilterRefresh,
}: UseTraceLifecycleParams) => {
  const { t } = useI18n()

  onMounted(async () => {
    try {
      await refresh()
    } catch (e: unknown) {
      ElMessage.error(e instanceof Error ? e.message : t("trace.messages.loadFailed"))
    }
  })

  onUnmounted(() => {
    clearPendingFilterRefresh()
  })
}
