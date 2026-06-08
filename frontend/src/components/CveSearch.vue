<template>
  <div class="security-page space-y-4 sm:space-y-6">
    <!-- 搜索区域 -->
    <div class="flex flex-col sm:flex-row gap-3">
      <el-input
        v-model="query"
        placeholder="输入 CVE 编号或关键字"
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
        placeholder="数据来源"
        clearable
        class="w-full sm:w-[150px]"
        @change="handleSourceChange"
      >
        <el-option label="全部" value="" />
        <el-option label="GitHub" value="github" />
        <el-option label="Exploit-DB" value="exploit-db" />
      </el-select>
    </div>

    <!-- 操作按钮 -->
    <div class="flex flex-col sm:flex-row gap-3">
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
      <el-button
        type="success"
        @click="handleUpdateDatabase"
        :loading="updating"
        :disabled="updating"
        class="w-full sm:w-auto"
      >
        <el-icon class="mr-1"><Refresh /></el-icon>
        更新数据库
      </el-button>
    </div>

    <!-- 更新状态提示 -->
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

    <!-- 结果表格 -->
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
            <el-table-column prop="cve_id" label="CVE 编号" width="130" sortable>
              <template #default="scope">
                <el-tag type="danger" size="small">{{ scope.row.cve_id }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="110" sortable>
              <template #default="scope">
                <el-tag v-if="scope.row.source === 'github'" type="success">
                  GitHub
                </el-tag>
                <el-tag v-else-if="scope.row.source === 'exploit-db'" type="warning">
                  Exploit-DB
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="github_url" label="链接" min-width="180">
              <template #default="scope">
                <a
                  :href="scope.row.github_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-blue-600 hover:text-blue-800 hover:underline text-sm break-all"
                >
                  {{ scope.row.github_url }}
                </a>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="200">
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
                      展开
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
                      收起
                    </el-button>
                  </div>
                </div>
                <span v-else class="text-gray-400 text-sm">-</span>
              </template>
            </el-table-column>
            <el-table-column
              prop="create_time"
              label="发现日期"
              width="140"
              sortable
              :formatter="formatDate"
            />
          </el-table>
        </div>
      </transition>

      <!-- 分页 -->
      <transition name="el-fade-in">
        <div class="mt-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div class="text-sm text-gray-500">
            显示 {{ filteredResults.length }} / {{ total }} 条结果
            <span v-if="sourceFilter">(已按来源筛选)</span>
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

    <!-- 空状态 -->
    <template v-else-if="searched">
      <transition name="el-fade-in">
        <el-empty
          description="未找到结果"
          :image-size="isMobile ? 100 : 120"
        >
          <template #description>
            <p class="text-gray-500">未找到符合条件的 CVE 记录</p>
            <p class="text-gray-400 text-sm mt-2">请尝试调整搜索条件</p>
          </template>
        </el-empty>
      </transition>
    </template>

    <template v-else>
      <div class="query-empty">
        <span class="query-empty-icon">
          <el-icon><Search /></el-icon>
        </span>
        <h4>等待检索条件</h4>
        <p>CVE 编号、组件名或漏洞关键词</p>
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
import { ref, computed, reactive, onMounted, onUnmounted } from "vue"
import { ElMessageBox } from "element-plus"
import { useCveApi } from "../composables/useApi"
import { usePagination } from "../composables/usePagination"
import { Search, Refresh } from "@element-plus/icons-vue"
import type { CveResult } from "../types"

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
const query = ref("")
const sourceFilter = ref("")
const results = ref<CveResult[]>([])
const searched = ref(false)
const expandedRows = reactive(new Set<number>())

// API hooks
const { loading, searchCve, updateDatabase } = useCveApi()
const updateMessage = ref<{
  type: 'success' | 'warning' | 'info' | 'error'
  title: string
  description: string
} | null>(null)
const updating = ref(false)
const sampleQueries = ["CVE-2024", "nginx", "spring"]

// 分页
const { currentPage, pageSize, total, setPage, setPageSize, setTotal } = usePagination()

// 计算属性
const isSearchDisabled = computed(() => {
  return !query.value || !query.value.trim()
})

const filteredResults = computed(() => {
  if (!sourceFilter.value) {
    return results.value
  }
  return results.value.filter(item => item.source === sourceFilter.value)
})

// 工具函数
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
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// 事件处理
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
      '更新会触发后端 CVE 数据同步任务，执行期间可能需要等待一段时间。',
      '更新 CVE 数据库',
      {
        confirmButtonText: '更新',
        cancelButtonText: '取消',
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
        title: '更新成功',
        description: `CVE 数据库已成功更新。新增: ${response.add_count} 条，删除: ${response.del_count} 条。`
      }
    } else {
      updateMessage.value = {
        type: 'error',
        title: '更新失败',
        description: response.message || '未知错误'
      }
    }
  } catch (error: unknown) {
    updateMessage.value = {
      type: 'error',
      title: '更新失败',
      description: error instanceof Error ? error.message : '网络错误'
    }
  } finally {
    updating.value = false
  }
}
</script>

<style scoped>
/* 响应式表格样式 */
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

/* 过渡动画 */
.el-table {
  transition: all 0.3s ease;
}

.query-empty {
  display: grid;
  min-height: 360px;
  place-items: center;
  align-content: center;
  border: 1px dashed #2a3a45;
  border-radius: 8px;
  color: #91a4b3;
  text-align: center;
}

.query-empty-icon {
  display: grid;
  width: 44px;
  height: 44px;
  place-items: center;
  border: 1px solid #22313a;
  border-radius: 8px;
  background: #0b151c;
  color: #8bd9ff;
}

.query-empty h4 {
  margin: 14px 0 4px;
  color: #dce7ef;
  font-size: 14px;
  font-weight: 700;
}

.query-empty p {
  margin: 0;
  font-size: 12px;
}

.sample-chip {
  cursor: pointer;
  border: 1px solid #2a3a45;
  border-radius: 8px;
  padding: 5px 10px;
  background: #0b151c;
  color: #91a4b3;
  font-size: 12px;
  transition: border-color 0.2s ease, color 0.2s ease, background 0.2s ease;
}

.sample-chip:hover,
.sample-chip:focus-visible {
  border-color: rgba(47, 143, 237, 0.6);
  background: #102638;
  color: #8bd9ff;
}

html:not(.dark) .query-empty {
  border-color: #cbd6e2;
  color: #64748b;
}

html:not(.dark) .query-empty-icon,
html:not(.dark) .sample-chip {
  border-color: #cbd6e2;
  background: #f8fafc;
}

html:not(.dark) .query-empty h4 {
  color: #0f172a;
}

html:not(.dark) .sample-chip {
  color: #475569;
}

html:not(.dark) .sample-chip:hover,
html:not(.dark) .sample-chip:focus-visible {
  border-color: rgba(47, 143, 237, 0.55);
  background: #eaf5ff;
  color: #0f4f8f;
}
</style>
