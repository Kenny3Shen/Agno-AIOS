<template>
  <div class="space-y-6">
    <div class="flex gap-4 flex-wrap">
      <el-input
        v-model="cveQuery"
        placeholder="CVE 编号 (例如: CVE-2024-1234)"
        class="flex-1 min-w-[200px]"
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
      <el-select v-model="sourceFilter" placeholder="数据来源" clearable class="w-[150px]">
        <el-option label="全部" value="" />
        <el-option label="GitHub" value="github" />
        <el-option label="Exploit-DB" value="exploit-db" />
      </el-select>
      <el-button type="primary" @click="handleSearch" :loading="loading" :disabled="isSearchDisabled || loading">搜索</el-button>
    </div>


    <el-table v-if="filteredResults.length > 0" :data="filteredResults" style="width: 100%" border stripe>
      <el-table-column prop="id" label="ID" width="80" sortable />
      <el-table-column prop="cve_id" label="CVE 编号" width="150" sortable />
      <el-table-column prop="source" label="来源" width="100" sortable>
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
import { Document } from "@element-plus/icons-vue"

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
    page: currentPage.value,
    size: pageSize.value
  })

  results.value = response.data.items
  total.value = response.data.total
  searched.value = true
  loading.value = false
}
</script>
