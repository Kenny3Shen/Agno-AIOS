import { reactive, ref } from "vue"
import { defineStore } from "pinia"
import type { CveResult } from "../types"

export type CollectTab = "markdown" | "preview"

export interface PageMessage {
  type: "success" | "warning" | "info" | "error"
  title: string
  description?: string
}

export const useSecurityDataStore = defineStore("securityData", () => {
  const cveQuery = ref("")
  const cveSourceFilter = ref("")
  const cveResults = ref<CveResult[]>([])
  const cveSearched = ref(false)
  const cveExpandedRows = reactive(new Set<number>())
  const cveUpdateMessage = ref<PageMessage | null>(null)
  const cveUpdating = ref(false)

  const collectActiveTab = ref<CollectTab>("markdown")
  const collectUrl = ref("")
  const collectMarkdownText = ref("")
  const collectMessage = ref<PageMessage | null>(null)

  const resetCollect = () => {
    collectUrl.value = ""
    collectMarkdownText.value = ""
    collectMessage.value = null
  }

  return {
    cveQuery,
    cveSourceFilter,
    cveResults,
    cveSearched,
    cveExpandedRows,
    cveUpdateMessage,
    cveUpdating,
    collectActiveTab,
    collectUrl,
    collectMarkdownText,
    collectMessage,
    resetCollect,
  }
})
