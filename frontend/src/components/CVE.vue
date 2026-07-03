<template>
  <div class="security-page space-y-4 sm:space-y-6">
    <div class="flex flex-col sm:flex-row gap-3">
      <el-input
        v-model="query"
        :placeholder="t('cve.input.queryPlaceholder')"
        class="flex-1 min-w-[200px]"
        @keyup.enter="handleSearch"
        clearable
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select
        v-model="sourceFilter"
        :placeholder="t('cve.input.sourcePlaceholder')"
        clearable
        class="w-full sm:w-[150px]"
        @change="handleSourceChange"
      >
        <el-option :label="t('cve.filters.all')" value="" />
        <el-option label="GitHub" value="github" />
        <el-option label="Exploit-DB" value="exploit-db" />
      </el-select>
    </div>

    <div class="flex flex-col sm:flex-row gap-3">
      <el-button
        type="primary"
        @click="handleSearch"
        :loading="loading"
        :disabled="isSearchDisabled || loading"
        class="w-full sm:w-auto"
      >
        <el-icon class="mr-1"><Search /></el-icon>
        {{ t('cve.actions.search') }}
      </el-button>
      <el-button
        type="success"
        @click="handleUpdateDatabase"
        :loading="updating"
        :disabled="updating"
        class="w-full sm:w-auto"
      >
        <el-icon class="mr-1"><Refresh /></el-icon>
        {{ t('cve.actions.updateDatabase') }}
      </el-button>
    </div>

    <transition name="el-fade-in-linear">
      <div v-if="updateMessage" class="mb-4">
        <el-alert
          :type="updateMessage.type"
          :title="updateMessage.title"
          :description="updateMessage.description"
          show-icon
          closable
          @close="updateMessage = null"
        />
      </div>
    </transition>

    <template v-if="filteredResults.length > 0">
      <transition name="el-fade-in">
        <div class="overflow-x-auto -mx-2 sm:mx-0">
          <el-table
            :data="filteredResults"
            style="width: 100%; min-width: 800px"
            border
            stripe
            :flexible="true"
          >
            <el-table-column prop="id" label="ID" width="70" sortable />
            <el-table-column prop="cve_id" :label="t('cve.table.cveId')" width="130" sortable>
              <template #default="scope">
                <el-tag type="danger" size="small">{{ scope.row.cve_id }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source" :label="t('cve.table.source')" width="110" sortable>
              <template #default="scope">
                <el-tag v-if="scope.row.source === 'github'" type="success">
                  GitHub
                </el-tag>
                <el-tag v-else-if="scope.row.source === 'exploit-db'" type="warning">
                  Exploit-DB
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="github_url" :label="t('cve.table.link')" min-width="180">
              <template #default="scope">
                <a
                  :href="scope.row.github_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="result-link"
                >
                  {{ scope.row.github_url }}
                </a>
              </template>
            </el-table-column>
            <el-table-column prop="description" :label="t('cve.table.description')" min-width="200">
              <template #default="scope">
                <div v-if="scope.row.description" class="text-sm">
                  <div v-if="!expandedRows.has(scope.row.id)">
                    <span>{{ truncateText(scope.row.description, 60) }}</span>
                    <el-button
                      v-if="scope.row.description.length > 60"
                      type="primary"
                      link
                      size="small"
                      @click="toggleExpand(scope.row.id)"
                    >
                      {{ t('cve.actions.expand') }}
                    </el-button>
                  </div>
                  <div v-else>
                    <span>{{ scope.row.description }}</span>
                    <el-button
                      type="primary"
                      link
                      size="small"
                      @click="toggleExpand(scope.row.id)"
                    >
                      {{ t('cve.actions.collapse') }}
                    </el-button>
                  </div>
                </div>
                <span v-else class="muted-inline">-</span>
              </template>
            </el-table-column>
            <el-table-column
              prop="create_time"
              :label="t('cve.table.discoveredAt')"
              width="140"
              sortable
              :formatter="formatDate"
            />
          </el-table>
        </div>
      </transition>

      <transition name="el-fade-in">
        <div class="mt-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div class="pagination-note">
            {{ t('cve.pagination.summary', { shown: filteredResults.length, total }) }}
            <span v-if="sourceFilter">{{ t('cve.filters.sourceFiltered') }}</span>
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
          :description="t('cve.empty.notFoundDescription')"
          :image-size="isMobile ? 100 : 120"
        >
          <template #description>
            <p class="empty-title">{{ t('cve.empty.notFoundTitle') }}</p>
            <p class="empty-hint">{{ t('cve.empty.notFoundHint') }}</p>
          </template>
        </el-empty>
      </transition>
    </template>

    <template v-else>
      <div class="query-empty">
        <span class="query-empty-icon">
          <el-icon><Search /></el-icon>
        </span>
        <h4>{{ t('cve.empty.waitingTitle') }}</h4>
        <p>{{ t('cve.empty.waitingHint') }}</p>
        <div class="mt-4 flex flex-wrap justify-center gap-2">
          <button
            v-for="sample in sampleQueries"
            :key="sample"
            type="button"
            class="sample-chip"
            @click="applySampleQuery(sample)"
          >
            {{ sample }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import { storeToRefs } from "pinia"
import { ElMessageBox } from "element-plus"
import { useCveApi } from "../composables/useApi"
import { usePagination } from "../composables/usePagination"
import { useSecurityDataStore } from "../stores/securityData"
import { useShellStore } from "../stores/shell"
import { Search, Refresh } from "@element-plus/icons-vue"
import type { CveResult } from "../types"

const { t, locale } = useI18n()
const shellStore = useShellStore()
const securityDataStore = useSecurityDataStore()

const isMobile = computed(() => shellStore.isMobile)

const {
  cveQuery: query,
  cveSourceFilter: sourceFilter,
  cveResults: results,
  cveSearched: searched,
  cveUpdateMessage: updateMessage,
  cveUpdating: updating,
} = storeToRefs(securityDataStore)
const expandedRows = securityDataStore.cveExpandedRows

const { loading, searchCve, updateDatabase } = useCveApi()
const sampleQueries = ["CVE-2024", "nginx", "spring"]

const { currentPage, pageSize, total, setPage, setPageSize, setTotal } = usePagination()

const isSearchDisabled = computed(() => {
  return !query.value || !query.value.trim()
})

const filteredResults = computed(() => {
  if (!sourceFilter.value) {
    return results.value
  }
  return results.value.filter(item => item.source === sourceFilter.value)
})

const truncateText = (text: string, maxLength: number) => {
  if (!text) return ""
  if (text.length <= maxLength) return text
  return text.substring(0, maxLength) + "..."
}

const toggleExpand = (id: number) => {
  if (expandedRows.has(id)) {
    expandedRows.delete(id)
  } else {
    expandedRows.add(id)
  }
}

const formatDate = (_row: CveResult, _column: unknown, cellValue: string) => {
  if (!cellValue) return ''
  const date = new Date(cellValue)
  return date.toLocaleString(locale.value, {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const handlePageChange = (page: number) => {
  setPage(page)
  handleSearch()
}

const handleSizeChange = (size: number) => {
  setPageSize(size)
  handleSearch()
}

const handleSourceChange = () => {
  currentPage.value = 1
  handleSearch()
}

const handleSearch = async () => {
  const hasQuery = query.value && query.value.trim()
  if (!hasQuery) return

  try {
    const data = await searchCve({
      query: query.value.trim(),
      source: sourceFilter.value || null,
      page: currentPage.value,
      size: pageSize.value
    })

    results.value = data.items
    setTotal(data.total)
    searched.value = true
    expandedRows.clear()
  } catch (error) {
    console.error('Search failed:', error)
  }
}

const applySampleQuery = (sample: string) => {
  query.value = sample
  currentPage.value = 1
  handleSearch()
}

const handleUpdateDatabase = async () => {
  try {
    await ElMessageBox.confirm(
      t('cve.confirm.updateMessage'),
      t('cve.confirm.updateTitle'),
      {
        confirmButtonText: t('cve.actions.update'),
        cancelButtonText: t('cve.actions.cancel'),
        type: 'warning'
      }
    )
  } catch (error) {
    if (error === 'cancel' || error === 'close') return
    throw error
  }

  updating.value = true
  updateMessage.value = null

  try {
    const response = await updateDatabase()

    if (response.status === 200) {
      updateMessage.value = {
        type: 'success',
        title: t('cve.messages.updateSuccessTitle'),
        description: t('cve.messages.updateSuccessDescription', {
          added: response.add_count,
          deleted: response.del_count
        })
      }
    } else {
      updateMessage.value = {
        type: 'error',
        title: t('cve.messages.updateFailedTitle'),
        description: response.message || t('cve.messages.unknownError')
      }
    }
  } catch (error: unknown) {
    updateMessage.value = {
      type: 'error',
      title: t('cve.messages.updateFailedTitle'),
      description: error instanceof Error ? error.message : t('cve.messages.networkError')
    }
  } finally {
    updating.value = false
  }
}
</script>

<style scoped>
/* Responsive table layout */
@media (max-width: 640px) {
  :deep(.el-table) {
    font-size: 12px;
  }

  :deep(.el-table .cell) {
    padding: 8px 6px;
  }

  :deep(.el-button--small) {
    padding: 4px 8px;
  }
}

/* Table transition */
.el-table {
  transition: all 0.3s ease;
}

</style>
