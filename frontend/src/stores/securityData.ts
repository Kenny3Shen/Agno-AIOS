import { reactive, ref } from "vue"
import { defineStore } from "pinia"
import type { AssetResult, CveResult } from "../types"

export type AssetSearchMode = "fingerprint" | "ip"
export type CollectTab = "markdown" | "preview"

export interface PageMessage {
  type: "success" | "warning" | "info" | "error"
  title: string
  description?: string
}

export const useSecurityDataStore = defineStore("securityData", () => {
  const assetQuery = ref("")
  const assetSearchMode = ref<AssetSearchMode>("fingerprint")
  const assetResults = ref<AssetResult[]>([])
  const assetSearched = ref(false)
  const assetSelectedIpType = ref<string | null>(null)
  const assetSelectedStatus = ref<number | null>(null)
  const assetSelectedTags = ref<string[]>([])

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

  const clearAssetFilters = () => {
    assetSelectedIpType.value = null
    assetSelectedStatus.value = null
    assetSelectedTags.value = []
  }

  const resetAssetSearch = () => {
    assetQuery.value = ""
    assetResults.value = []
    assetSearched.value = false
    clearAssetFilters()
  }

  const resetCollect = () => {
    collectUrl.value = ""
    collectMarkdownText.value = ""
    collectMessage.value = null
  }

  return {
    assetQuery,
    assetSearchMode,
    assetResults,
    assetSearched,
    assetSelectedIpType,
    assetSelectedStatus,
    assetSelectedTags,
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
    clearAssetFilters,
    resetAssetSearch,
    resetCollect,
  }
})
