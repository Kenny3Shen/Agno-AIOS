<template>
  <div class="space-y-6">
    <div class="flex gap-4">
      <el-input
        v-model="assetQuery"
        placeholder="输入指纹信息 (例如: Vue、React)"
        class="w-full"
        @keyup.enter="handleSearch"
        clearable
      >
        <template #prefix>
          <el-icon><Monitor /></el-icon>
        </template>
      </el-input>
      <el-button type="primary" @click="handleSearch" :loading="loading" :disabled="isSearchDisabled || loading">搜索</el-button>
    </div>

    <el-table v-if="allResults.length > 0" :data="paginatedResults" style="width: 100%" border stripe>
      <el-table-column prop="site" label="站点" width="220" fixed>
        <template #default="scope">
          <a :href="scope.row.site" target="_blank" class="text-blue-600 hover:underline">
            {{ scope.row.site }}
          </a>
        </template>
      </el-table-column>
      <el-table-column prop="ip" label="IP 地址" width="140" />
      <el-table-column prop="hostname" label="主机名" width="140" />
      <el-table-column prop="ip_type" label="IP 类型" width="100" />
      <el-table-column prop="status" label="状态码" width="90" />
      <el-table-column prop="finger" label="指纹" width="200">
        <template #default="scope">
          <el-tag
          v-for="(f, i) in getTopFingers(scope.row)"
          :key="f.name + i"
          :type="f.matched ? 'primary' : 'info'"
          size="small"
          class="mr-1 mb-1"
          >
          {{ f.name }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="tag" label="标签" width="100">
      <template #default="scope">
        <el-tag 
        v-for="(t, i) in scope.row.tag" 
        :key="i" 
        size="small" 
        :type="t === '无效' ? 'info' : 'success'"
        class="mr-1 mb-1"
        >
        {{ t }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="port_info" label="端口信息" width="200">
        <template #default="scope">
          <div v-if="scope.row.port_info && scope.row.port_info.length > 0" class="text-sm">
            {{ scope.row.port_info.slice(0, 5).join(', ') }}
            <span v-if="scope.row.port_info.length > 5" class="text-gray-500">
              ... (+{{ scope.row.port_info.length - 5 }})
            </span>
          </div>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" width="180" show-overflow-tooltip />
      <el-table-column prop="http_server" label="服务器" width="150" show-overflow-tooltip />
      <el-table-column prop="os_info" label="操作系统" width="180">
        <template #default="scope">
          <div v-if="scope.row.os_info && scope.row.os_info.length > 0">
            <div v-for="(os, i) in scope.row.os_info" :key="i" class="text-sm">{{ os }}</div>
          </div>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="domain" label="域名" width="180">
        <template #default="scope">
          <div v-if="scope.row.domain && scope.row.domain.length > 0">
            <div v-for="(d, i) in scope.row.domain.slice(0, 3)" :key="i" class="text-sm">{{ d }}</div>
            <span v-if="scope.row.domain.length > 3" class="text-gray-500 text-xs">
              +{{ scope.row.domain.length - 3 }} 更多
            </span>
          </div>
          <span v-else class="text-gray-400">-</span>
        </template>
      </el-table-column>
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

    <el-empty v-else-if="searched" description="未找到资产" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue"
import axios from "axios"
import { ElMessage } from "element-plus"

interface AssetResult {
  site: string
  hostname: string
  ip: string
  title: string
  status: number
  http_server: string
  finger: string[]
  tag: string[]
  port_info: number[]
  os_info: string[]
  ip_type: string
  domain: string[]
}

const assetQuery = ref("")
// results is unused; use allResults for client-side pagination
const allResults = ref<AssetResult[]>([]) // Cache all results for client-side pagination
const loading = ref(false)
const searched = ref(false)
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)

const isSearchDisabled = computed(() => !assetQuery.value || !assetQuery.value.trim())

const paginatedResults = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return allResults.value.slice(start, end)
})

const handlePageChange = (page: number) => {
  currentPage.value = page
  // No API call needed - data is already cached in allResults
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  // No API call needed - data is already cached in allResults
}

// Returns top 5 fingerprint display items. The searched fingerprint (assetQuery)
// is prioritized and shown as the first tag if found (exact match or contains).
const getTopFingers = (row: AssetResult) => {
  const q = assetQuery.value?.trim().toLowerCase()
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

const handleSearch = async () => {
  if (!assetQuery.value || !assetQuery.value.trim()) return
  
  loading.value = true
  searched.value = false
  // removed results.value clearing - we use allResults
  allResults.value = []
  currentPage.value = 1 // Reset to first page
  
  try {
    const { data } = await axios.post("/api/asset/search", {
      fingerprint: assetQuery.value,
      page: 1, // Keep for backward compatibility, but backend ignores
      size: 10,
    })
    if (data.status === 200) {
      allResults.value = data.items // Cache all results
      total.value = data.total
      searched.value = true
    } else {
      ElMessage.error("搜索失败: " + data.message)
    }
  } catch (error: any) {
    console.error(error)
    ElMessage.error("获取资产数据失败: " + (error?.message || error))
  } finally {
    loading.value = false
  }
}
</script>
