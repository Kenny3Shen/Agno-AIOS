<template>
  <div class="space-y-6">
    <div class="flex gap-4">
      <el-input
        v-model="searchQuery"
        placeholder="输入 CVE 编号 (例如: CVE-2024-1234)"
        class="w-full"
        @keyup.enter="handleSearch"
        clearable
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button type="primary" @click="handleSearch" :loading="loading" :disabled="isSearchDisabled || loading">搜索</el-button>
    </div>

    <el-table v-if="results.length > 0" :data="results" style="width: 100%" border stripe>
      <el-table-column prop="id" label="ID" width="100" sortable />
      <el-table-column prop="cve_id" label="CVE 编号" width="150" sortable />
      <el-table-column prop="github_url" label="GitHub 链接" min-width="350">
        <template #default="scope">
          <a :href="scope.row.github_url" target="_blank" class="text-blue-600 hover:underline">
            {{ scope.row.github_url }}
          </a>
        </template>
      </el-table-column>
      <el-table-column prop="create_time" label="发现日期" width="160" sortable :formatter="formatDate" />
    </el-table>

    <el-pagination
      v-if="total > 0"
      v-model:current-page="currentPage"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[10, 20, 50, 100]"
      layout="total, sizes, prev, pager, next, jumper"
      class="mt-4 justify-center"
      @current-change="handlePageChange"
      @size-change="handleSizeChange"
    />

    <el-empty v-else-if="searched" description="未找到结果" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue"
import axios from "axios"

interface CveResult {
  id: number
  cve_id: string
  github_url: string
  create_time: string
}

const searchQuery = ref("")
const results = ref<CveResult[]>([])
const loading = ref(false)
const searched = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)

const isSearchDisabled = computed(() => !searchQuery.value || !searchQuery.value.trim())

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
  if (!searchQuery.value || !searchQuery.value.trim()) return
  
  loading.value = true
  searched.value = false
  results.value = []
  
  const response = await axios.post("/api/cve/search", {
    cve_id: searchQuery.value,
    page: currentPage.value,
    size: pageSize.value
  })

  results.value = response.data.items
  total.value = response.data.total
  searched.value = true
  loading.value = false
}
</script>
