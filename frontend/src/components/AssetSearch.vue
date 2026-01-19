<template>
  <div class="space-y-4 sm:space-y-6">
    <!-- 搜索 & 筛选区域 -->
    <div class="rounded-xl border border-slate-200/70 bg-white/80 p-3 sm:p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
      <div class="flex flex-col sm:flex-row gap-3">
        <el-radio-group v-model="searchMode" class="shrink-0" size="default">
          <el-radio-button label="fingerprint">指纹</el-radio-button>
          <el-radio-button label="ip">IP</el-radio-button>
        </el-radio-group>

        <el-input
          v-model="assetQuery"
          :placeholder="searchMode === 'ip' ? '输入 IP 地址 (例如: 192.168.1.1)' : '输入指纹信息 (例如: Vue、React)'"
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
          搜索
        </el-button>
      </div>

      <!-- 筛选（基于结果的本地筛选） -->
      <transition name="el-fade-in">
        <div v-if="allResults.length > 0" class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <el-select
            v-model="selectedIpType"
            clearable
            filterable
            placeholder="IP 类型"
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
            placeholder="状态码"
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
            placeholder="标签（可多选）"
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
            清空筛选
          </el-button>
        </div>
      </transition>
    </div>

    <!-- 结果表格 -->
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
            <el-table-column prop="site" label="站点" width="180" fixed>
              <template #default="scope">
                <a
                  :href="scope.row.site"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-blue-600 hover:text-blue-800 hover:underline text-sm break-all"
                >
                  {{ scope.row.site }}
                </a>
              </template>
            </el-table-column>
            <el-table-column prop="ip" label="IP 地址" width="120" />
            <el-table-column prop="hostname" label="主机名" width="120" show-overflow-tooltip />
            <el-table-column prop="ip_type" label="IP 类型" width="80" />
            <el-table-column prop="status" label="状态码" width="70">
              <template #default="scope">
                <el-tag
                  :type="getStatusType(scope.row.status)"
                  size="small"
                >
                  {{ scope.row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="finger" label="指纹" width="180">
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
            <el-table-column prop="tag" label="标签" width="90">
              <template #default="scope">
                <div class="flex flex-wrap gap-1">
                  <el-tag
                    v-for="(t, i) in scope.row.tag"
                    :key="i"
                    size="small"
                    :type="t === '无效' ? 'info' : 'success'"
                    class="text-xs"
                  >
                    {{ t }}
                  </el-tag>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="port_info" label="端口信息" width="150">
              <template #default="scope">
                <div v-if="scope.row.port_info && scope.row.port_info.length > 0" class="text-sm">
                  {{ scope.row.port_info.slice(0, 4).join(', ') }}
                  <span v-if="scope.row.port_info.length > 4" class="text-gray-500">
                    ... (+{{ scope.row.port_info.length - 4 }})
                  </span>
                </div>
                <span v-else class="text-gray-400 text-sm">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" width="150" show-overflow-tooltip />
            <el-table-column prop="http_server" label="服务器" width="120" show-overflow-tooltip />
            <el-table-column prop="os_info" label="操作系统" width="140">
              <template #default="scope">
                <div v-if="scope.row.os_info && scope.row.os_info.length > 0">
                  <div v-for="(os, i) in scope.row.os_info.slice(0, 2)" :key="i" class="text-xs">
                    {{ os }}
                  </div>
                  <span v-if="scope.row.os_info.length > 2" class="text-gray-500 text-xs">
                    +{{ scope.row.os_info.length - 2 }}
                  </span>
                </div>
                <span v-else class="text-gray-400 text-sm">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="domain" label="域名" width="140">
              <template #default="scope">
                <div v-if="scope.row.domain && scope.row.domain.length > 0">
                  <div v-for="(d, i) in scope.row.domain.slice(0, 2)" :key="i" class="text-xs">
                    {{ d }}
                  </div>
                  <span v-if="scope.row.domain.length > 2" class="text-gray-500 text-xs">
                    +{{ scope.row.domain.length - 2 }}
                  </span>
                </div>
                <span v-else class="text-gray-400 text-sm">-</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </transition>

      <!-- 分页 -->
      <transition name="el-fade-in">
        <div class="mt-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div class="text-sm text-gray-500">
            共 {{ total }} 条资产，当前显示 {{ paginatedResults.length }} 条
          </div>
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            :small="isMobile"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </transition>
    </template>

    <!-- 空状态 -->
    <template v-else-if="searched">
      <transition name="el-fade-in">
        <el-empty
          description="未找到资产"
          :image-size="isMobile ? 100 : 120"
        >
          <template #description>
            <p class="text-gray-500">未找到符合条件的资产</p>
            <p class="text-gray-400 text-sm mt-2">请尝试其他指纹关键词</p>
          </template>
        </el-empty>
      </transition>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from "vue"
import { useAssetApi } from "../composables/useApi"
import { usePagination } from "../composables/usePagination"
import { Monitor, Search } from "@element-plus/icons-vue"
import type { AssetResult } from "../types"

// 响应式检测
const isMobile = ref(false)
const checkMobile = () => {
  isMobile.value = window.innerWidth < 640
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

// 查询状态
const assetQuery = ref("")
const searchMode = ref<"fingerprint" | "ip">("fingerprint")
const allResults = ref<AssetResult[]>([])
const searched = ref(false)

// 筛选状态
const selectedIpType = ref<string | null>(null)
const selectedStatus = ref<number | null>(null)
const selectedTags = ref<string[]>([])

// API hooks
const { loading, searchAsset } = useAssetApi()

// 分页
const { currentPage, pageSize, total, setPage, setPageSize, setTotal } = usePagination()

// 计算属性
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

// 工具函数
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
  selectedIpType.value = null
  selectedStatus.value = null
  selectedTags.value = []
  setPage(1)
}

watch([filteredResults, pageSize], () => {
  setTotal(filteredResults.value.length)
})

watch([selectedIpType, selectedStatus, selectedTags], () => {
  setPage(1)
})

watch(searchMode, () => {
  assetQuery.value = ''
  allResults.value = []
  searched.value = false
  clearFilters()
  setTotal(0)
})

// 事件处理
const handlePageChange = (page: number) => {
  setPage(page)
}

const handleSizeChange = (size: number) => {
  setPageSize(size)
}

const handleSearch = async () => {
  if (!assetQuery.value || !assetQuery.value.trim()) return

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
  } catch (error: any) {
    console.error('Search failed:', error)
  }
}
</script>

<style scoped>
/* 响应式表格样式 */
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
