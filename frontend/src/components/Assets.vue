<template>
  <div class="security-page space-y-4 sm:space-y-6">
    <div class="query-panel">
      <div class="flex flex-col sm:flex-row gap-3">
        <el-radio-group v-model="searchMode" class="shrink-0" size="default">
          <el-radio-button value="fingerprint">{{ t('assets.modes.fingerprint') }}</el-radio-button>
          <el-radio-button value="ip">IP</el-radio-button>
        </el-radio-group>

        <el-input
          v-model="assetQuery"
          :placeholder="searchMode === 'ip' ? t('assets.input.ipPlaceholder') : t('assets.input.fingerprintPlaceholder')"
          class="flex-1"
          @keyup.enter="handleSearch"
          clearable
        >
          <template #prefix>
            <el-icon><Monitor /></el-icon>
          </template>
        </el-input>

        <el-button
          type="primary"
          @click="handleSearch"
          :loading="loading"
          :disabled="isSearchDisabled || loading"
          class="w-full sm:w-auto"
        >
          <el-icon class="mr-1"><Search /></el-icon>
          {{ t('assets.actions.search') }}
        </el-button>
      </div>

      <div v-if="validationNotice" class="validation-notice">
        {{ validationNotice }}
      </div>

      <transition name="el-fade-in">
        <div v-if="allResults.length > 0" class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <el-select
            v-model="selectedIpType"
            clearable
            filterable
            :placeholder="t('assets.filters.ipType')"
            class="w-full"
          >
            <el-option
              v-for="t in ipTypeOptions"
              :key="t"
              :label="t"
              :value="t"
            />
          </el-select>

          <el-select
            v-model="selectedStatus"
            clearable
            filterable
            :placeholder="t('assets.filters.statusCode')"
            class="w-full"
          >
            <el-option
              v-for="s in statusOptions"
              :key="s"
              :label="String(s)"
              :value="s"
            />
          </el-select>

          <el-select
            v-model="selectedTags"
            multiple
            collapse-tags
            collapse-tags-tooltip
            clearable
            filterable
            :placeholder="t('assets.filters.tags')"
            class="w-full"
          >
            <el-option
              v-for="t in tagOptions"
              :key="t"
              :label="t"
              :value="t"
            />
          </el-select>

          <el-button class="w-full" @click="clearFilters" :disabled="!hasActiveFilters">
            {{ t('assets.filters.clear') }}
          </el-button>
        </div>
      </transition>
    </div>

    <template v-if="allResults.length > 0">
      <transition name="el-fade-in">
        <div class="overflow-x-auto -mx-2 sm:mx-0">
          <el-table
            :data="paginatedResults"
            style="width: 100%; min-width: 1000px"
            border
            stripe
            :flexible="true"
          >
            <el-table-column prop="site" :label="t('assets.table.site')" width="180" fixed>
              <template #default="scope">
                <a
                  :href="scope.row.site"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="result-link"
                >
                  {{ scope.row.site }}
                </a>
              </template>
            </el-table-column>
            <el-table-column prop="ip" :label="t('assets.table.ipAddress')" width="120" />
            <el-table-column prop="hostname" :label="t('assets.table.hostname')" width="120" show-overflow-tooltip />
            <el-table-column prop="ip_type" :label="t('assets.table.ipType')" width="80" />
            <el-table-column prop="status" :label="t('assets.table.statusCode')" width="70">
              <template #default="scope">
                <el-tag
                  :type="getStatusType(scope.row.status)"
                  size="small"
                >
                  {{ scope.row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="finger" :label="t('assets.table.fingerprint')" width="180">
              <template #default="scope">
                <div class="flex flex-wrap gap-1">
                  <el-tag
                    v-for="(f, i) in getTopFingers(scope.row)"
                    :key="f.name + i"
                    :type="f.matched ? 'primary' : 'info'"
                    size="small"
                    class="text-xs"
                  >
                    {{ f.name }}
                  </el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="tag" :label="t('assets.table.tag')" width="90">
              <template #default="scope">
                <div class="flex flex-wrap gap-1">
                  <el-tag
                    v-for="(tag, i) in scope.row.tag"
                    :key="i"
                    size="small"
                    :type="tag === INVALID_ASSET_TAG ? 'info' : 'success'"
                    class="text-xs"
                  >
                    {{ tag }}
                  </el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="port_info" :label="t('assets.table.portInfo')" width="150">
              <template #default="scope">
                <div v-if="scope.row.port_info && scope.row.port_info.length > 0" class="text-sm">
                  {{ scope.row.port_info.slice(0, 4).join(', ') }}
                  <span v-if="scope.row.port_info.length > 4" class="muted-inline">
                    ... (+{{ scope.row.port_info.length - 4 }})
                  </span>
                </div>
                <span v-else class="muted-inline">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="title" :label="t('assets.table.title')" width="150" show-overflow-tooltip />
            <el-table-column prop="http_server" :label="t('assets.table.server')" width="120" show-overflow-tooltip />
            <el-table-column prop="os_info" :label="t('assets.table.os')" width="140">
              <template #default="scope">
                <div v-if="scope.row.os_info && scope.row.os_info.length > 0">
                  <div v-for="(os, i) in scope.row.os_info.slice(0, 2)" :key="i" class="text-xs">
                    {{ os }}
                  </div>
                  <span v-if="scope.row.os_info.length > 2" class="muted-inline">
                    +{{ scope.row.os_info.length - 2 }}
                  </span>
                </div>
                <span v-else class="muted-inline">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="domain" :label="t('assets.table.domain')" width="140">
              <template #default="scope">
                <div v-if="scope.row.domain && scope.row.domain.length > 0">
                  <div v-for="(d, i) in scope.row.domain.slice(0, 2)" :key="i" class="text-xs">
                    {{ d }}
                  </div>
                  <span v-if="scope.row.domain.length > 2" class="muted-inline">
                    +{{ scope.row.domain.length - 2 }}
                  </span>
                </div>
                <span v-else class="muted-inline">-</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </transition>

      <transition name="el-fade-in">
        <div class="mt-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div class="pagination-note">
            {{ t('assets.pagination.summary', { total, shown: paginatedResults.length }) }}
          </div>
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            :size="isMobile ? 'small' : 'default'"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </transition>
    </template>

    <template v-else-if="searched">
      <transition name="el-fade-in">
        <el-empty
          :description="t('assets.empty.notFoundDescription')"
          :image-size="isMobile ? 100 : 120"
        >
          <template #description>
            <p class="empty-title">{{ t('assets.empty.notFoundTitle') }}</p>
            <p class="empty-hint">{{ t('assets.empty.notFoundHint') }}</p>
          </template>
        </el-empty>
      </transition>
    </template>

    <template v-else>
      <div class="query-empty">
        <span class="query-empty-icon">
          <el-icon><Monitor /></el-icon>
        </span>
        <h4>{{ t('assets.empty.waitingTitle') }}</h4>
        <p>{{ searchMode === 'ip' ? t('assets.empty.waitingIp') : t('assets.empty.waitingFingerprint') }}</p>
        <div class="mt-4 flex flex-wrap justify-center gap-2">
          <button
            v-for="sample in activeSamples"
            :key="sample.label"
            type="button"
            class="sample-chip"
            @click="applySampleQuery(sample)"
          >
            {{ sample.label }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from "vue"
import { useI18n } from "vue-i18n"
import { storeToRefs } from "pinia"
import { useAssetApi } from "../composables/useApi"
import { usePagination } from "../composables/usePagination"
import { useSecurityDataStore } from "../stores/securityData"
import { useShellStore } from "../stores/shell"
import { Monitor, Search } from "@element-plus/icons-vue"
import type { AssetResult } from "../types"

const { t } = useI18n()
const INVALID_ASSET_TAG = "\u65e0\u6548"
const shellStore = useShellStore()
const securityDataStore = useSecurityDataStore()

const isMobile = computed(() => shellStore.isMobile)

const {
  assetQuery,
  assetSearchMode: searchMode,
  assetResults: allResults,
  assetSearched: searched,
  assetSelectedIpType: selectedIpType,
  assetSelectedStatus: selectedStatus,
  assetSelectedTags: selectedTags,
} = storeToRefs(securityDataStore)

const fingerprintSamples = [
  { label: "Vue", mode: "fingerprint" as const, value: "Vue" },
  { label: "React", mode: "fingerprint" as const, value: "React" },
  { label: "nginx", mode: "fingerprint" as const, value: "nginx" },
]
const ipSamples = [
  { label: "10.192.20.170", mode: "ip" as const, value: "10.192.20.170" },
  { label: "47.99.2.74", mode: "ip" as const, value: "47.99.2.74" },
]

const { loading, searchAsset } = useAssetApi()

const { currentPage, pageSize, total, setPage, setPageSize, setTotal } = usePagination()

const isValidIpv4 = (value: string) => {
  const s = value.trim()
  if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(s)) return false
  return s.split('.').every((p) => {
    const n = Number(p)
    return Number.isInteger(n) && n >= 0 && n <= 255
  })
}

const isSearchDisabled = computed(() => {
  const q = assetQuery.value?.trim()
  if (!q) return true
  if (searchMode.value === 'ip') return !isValidIpv4(q)
  return false
})

const validationNotice = computed(() => {
  const q = assetQuery.value?.trim()
  if (!q || searchMode.value !== 'ip' || isValidIpv4(q)) return ''
  return t('assets.validation.ipv4Only')
})

const activeSamples = computed(() => searchMode.value === 'ip' ? ipSamples : fingerprintSamples)

const ipTypeOptions = computed(() => {
  const set = new Set<string>()
  for (const r of allResults.value) {
    if (r?.ip_type) set.add(r.ip_type)
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b))
})

const statusOptions = computed(() => {
  const set = new Set<number>()
  for (const r of allResults.value) {
    if (typeof r?.status === 'number') set.add(r.status)
  }
  return Array.from(set).sort((a, b) => a - b)
})

const tagOptions = computed(() => {
  const set = new Set<string>()
  for (const r of allResults.value) {
    if (Array.isArray(r?.tag)) {
      for (const t of r.tag) {
        if (t) set.add(t)
      }
    }
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b))
})

const hasActiveFilters = computed(() => {
  return Boolean(selectedIpType.value || selectedStatus.value || (selectedTags.value && selectedTags.value.length > 0))
})

const filteredResults = computed(() => {
  let results = allResults.value

  if (selectedIpType.value) {
    results = results.filter((r) => r.ip_type === selectedIpType.value)
  }

  if (selectedStatus.value !== null) {
    results = results.filter((r) => r.status === selectedStatus.value)
  }

  if (selectedTags.value && selectedTags.value.length > 0) {
    const required = new Set(selectedTags.value)
    results = results.filter((r) => {
      const tags = Array.isArray(r.tag) ? r.tag : []
      for (const t of required) {
        if (!tags.includes(t)) return false
      }
      return true
    })
  }

  return results
})

const paginatedResults = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredResults.value.slice(start, end)
})

const getStatusType = (status: number) => {
  if (status >= 200 && status < 300) return 'success'
  if (status >= 300 && status < 400) return 'warning'
  if (status >= 400 && status < 500) return 'danger'
  if (status >= 500) return 'danger'
  return 'info'
}

// Returns top 5 fingerprint display items. The searched fingerprint (assetQuery)
// is prioritized and shown as the first tag if found (exact match or contains).
const getTopFingers = (row: AssetResult) => {
  const q = searchMode.value === 'fingerprint' ? assetQuery.value?.trim().toLowerCase() : ''
  const fingers = Array.isArray(row.finger) ? [...new Set(row.finger)] : []
  let matchedName: string | null = null
  if (q) {
    // prefer exact match, otherwise accept substring
    let matchIndex = fingers.findIndex((f) => f && f.toLowerCase() === q)
    if (matchIndex === -1) matchIndex = fingers.findIndex((f) => f && f.toLowerCase().includes(q))
    if (matchIndex !== -1) {
      const m = fingers.splice(matchIndex, 1)[0]
      matchedName = m ?? null
    }
  }
  const out: { name: string; matched: boolean }[] = []
  if (matchedName) out.push({ name: matchedName, matched: true })
  for (const f of fingers.slice(0, 5 - out.length)) {
    out.push({ name: f, matched: false })
  }
  return out
}

const clearFilters = () => {
  securityDataStore.clearAssetFilters()
  setPage(1)
}

watch([filteredResults, pageSize], () => {
  setTotal(filteredResults.value.length)
})

watch([selectedIpType, selectedStatus, selectedTags], () => {
  setPage(1)
})

watch(searchMode, () => {
  securityDataStore.resetAssetSearch()
  setPage(1)
  setTotal(0)
}, { flush: "sync" })

const handlePageChange = (page: number) => {
  setPage(page)
}

const handleSizeChange = (size: number) => {
  setPageSize(size)
}

const handleSearch = async () => {
  if (isSearchDisabled.value) return

  try {
    const q = assetQuery.value.trim()
    const data = await searchAsset(
      searchMode.value === 'ip'
        ? { ip: q, page: 1, size: 10 }
        : { fingerprint: q, page: 1, size: 10 }
    )

    if (data.status === 200) {
      allResults.value = data.items
      searched.value = true
      clearFilters()
      setTotal(data.total)
    }
  } catch (error: unknown) {
    console.error('Search failed:', error)
  }
}

const applySampleQuery = (sample: (typeof fingerprintSamples)[number] | (typeof ipSamples)[number]) => {
  searchMode.value = sample.mode
  assetQuery.value = sample.value
  setPage(1)
  handleSearch()
}
</script>

<style scoped>
/* Responsive table layout */
@media (max-width: 640px) {
  :deep(.el-table) {
    font-size: 11px;
  }

  :deep(.el-table .cell) {
    padding: 6px 4px;
  }

  :deep(.el-tag--small) {
    height: 18px;
    line-height: 18px;
    padding: 0 6px;
    font-size: 10px;
  }
}

</style>
