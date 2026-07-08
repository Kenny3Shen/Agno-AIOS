import { reactive } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { copyToClipboard } from "../lib/clipboard"
import { tracePayloadTextForMode, type TracePayloadViewMode } from "../modules/traceWorkbench"
import type { ParsedSpanPayload } from "../types"

export type TracePayloadKey = "input" | "output"

export const useTracePayloadControls = () => {
  const { t } = useI18n()
  const expandedPayloads = reactive(new Set<TracePayloadKey>())

  const copyText = async (text: string) => {
    const trimmedText = (text || "").trim()
    if (!trimmedText) return
    if (await copyToClipboard(trimmedText)) {
      ElMessage.success(t("common.clipboard.copied"))
    } else {
      ElMessage.warning(t("common.clipboard.failed"))
    }
  }

  const copyPayload = async (payload: ParsedSpanPayload, mode: TracePayloadViewMode) => {
    await copyText(tracePayloadTextForMode(payload, mode, ""))
  }

  const copyMetadataValue = async (value: string) => {
    if (!value || value === "-") return
    await copyText(value)
  }

  const togglePayloadExpanded = (key: TracePayloadKey) => {
    if (expandedPayloads.has(key)) {
      expandedPayloads.delete(key)
    } else {
      expandedPayloads.add(key)
    }
  }

  return {
    expandedPayloads,
    copyPayload,
    copyMetadataValue,
    togglePayloadExpanded,
  }
}
