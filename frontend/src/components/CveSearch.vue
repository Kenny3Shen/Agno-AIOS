<template>
  <div class="space-y-6">
    <div class="flex gap-4 flex-wrap">
      <el-input
        v-model="cveQuery"
        placeholder="CVE-2024-1234"
        class="flex-1 min-w-[150px]"
        @keyup.enter="handleSearch"
        clearable
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-input
        v-model="keywordQuery"
        placeholder="关键字搜索描述"
        class="flex-1 min-w-[200px]"
        @keyup.enter="handleSearch"
        clearable
      >
        <template #prefix>
          <el-icon><Document /></el-icon>
        </template>
      </el-input>
      <el-select v-model="sourceFilter" placeholder="数据来源" clearable class="w-[150px]" @change="handleSourceChange">
        <el-option label="全部" value="" />
        <el-option label="GitHub" value="github" />
        <el-option label="Exploit-DB" value="exploit-db" />
      </el-select>
      <el-button type="primary" @click="handleSearch" :loading="loading" :disabled="isSearchDisabled || loading">搜索</el-button>
      <el-button type="success" @click="handleUpdateDatabase" :loading="updating" :disabled="updating">更新</el-button>
    </div>

    <!-- 更新状态提示 -->
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


    <el-table v-if="filteredResults.length > 0" :data="filteredResults" style="width: 100%" border stripe>
      <el-table-column prop="id" label="ID" width="70" sortable />
      <el-table-column prop="cve_id" label="CVE 编号" width="150" sortable />
      <el-table-column prop="source" label="来源" width="120" sortable>
        <template #default="scope">
          <el-tag v-if="scope.row.source === 'github'" type="success">GitHub</el-tag>
          <el-tag v-else-if="scope.row.source === 'exploit-db'" type="warning">Exploit-DB</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="github_url" label="链接" min-width="200">
        <template #default="scope">
          <a :href="scope.row.github_url" target="_blank" class="text-blue-600 hover:underline">
            {{ scope.row.github_url }}
          </a>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="250">
        <template #default="scope">
          <div v-if="scope.row.description">
            <div v-if="!expandedRows.has(scope.row.id)">
              <span>{{ truncateText(scope.row.description, 50) }}</span>
              <el-button
                v-if="scope.row.description.length > 50"
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
              <el-button type="primary" link size="small" @click="toggleExpand(scope.row.id)">
                收起
              </el-button>
            </div>
          </div>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" label="发现日期" width="160" sortable :formatter="formatDate" />
    </el-table>

    <div v-if="total > 0" class="mt-4 flex items-center justify-between">
      <div class="text-sm text-gray-500">
        显示 {{ filteredResults.length }} / {{ total }} 条结果
        <span v-if="sourceFilter">(已按来源筛选)</span>
      </div>
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="sizes, prev, pager, next, jumper"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </div>

    <el-empty v-else-if="searched" description="未找到结果" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from "vue"
import axios from "axios"
import { Document, Search } from "@element-plus/icons-vue"

interface CveResult {
  id: number
  cve_id: string
  github_url: string
  description: string
  source: string
  create_time: string
}

const cveQuery = ref("")
const keywordQuery = ref("")
const sourceFilter = ref("")
const results = ref<CveResult[]>([])
const loading = ref(false)
const searched = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)
const expandedRows = reactive(new Set<number>())
const updating = ref(false)
const updateMessage = ref<{
  type: 'success' | 'warning' | 'info' | 'error'
  title: string
  description: string
} | null>(null)

// 两个查询框均为空时禁用搜索按钮
const isSearchDisabled = computed(() => {
  const hasCve = cveQuery.value && cveQuery.value.trim()
  const hasKeyword = keywordQuery.value && keywordQuery.value.trim()
  return !hasCve && !hasKeyword
})

// 前端过滤结果（根据来源筛选）
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

const formatDate = (_: CveResult, __: any, cellValue: string) => {
  if (!cellValue) return ''
  const date = new Date(cellValue)
  return date.toLocaleString('zh-CN', { hour12: false })
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  handleSearch()
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  handleSearch()
}

const handleSourceChange = (value: string) => {
  sourceFilter.value = value
  currentPage.value = 1
  handleSearch()
}

const handleSearch = async () => {
  const hasCve = cveQuery.value && cveQuery.value.trim()
  const hasKeyword = keywordQuery.value && keywordQuery.value.trim()
  if (!hasCve && !hasKeyword) return
  
  loading.value = true
  searched.value = false
  results.value = []
  expandedRows.clear()
  
  const response = await axios.post("/api/cve/search", {
    cve_id: hasCve ? cveQuery.value.trim() : null,
    keyword: hasKeyword ? keywordQuery.value.trim() : null,
    source: sourceFilter.value || null,
    page: currentPage.value,
    size: pageSize.value
  })

  results.value = response.data.items
  total.value = response.data.total
  searched.value = true
  loading.value = false
}

const handleUpdateDatabase = async () => {
  updating.value = true
  updateMessage.value = null

  try {
    const response = await axios.post("/api/cve/update")
    
    if (response.data.status === 200) {
      updateMessage.value = {
        type: 'success',
        title: '更新成功',
        description: `CVE 数据库已成功更新。新增: ${response.data.add_count} 条，删除: ${response.data.del_count} 条。`
      }
    } else {
      updateMessage.value = {
        type: 'error',
        title: '更新失败',
        description: response.data.message || '未知错误'
      }
    }
  } catch (error: any) {
    updateMessage.value = {
      type: 'error',
      title: '更新失败',
      description: error.response?.data?.message || error.message || '网络错误'
    }
  } finally {
    updating.value = false
  }
}
</script>
