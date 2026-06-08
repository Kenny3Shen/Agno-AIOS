<template>
  <div class="security-page space-y-5 max-w-5xl mx-auto">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between">
      <div>
        <h3 class="text-base font-semibold text-slate-900 dark:text-[#C9D1D9]">Skills 管理</h3>
        <p class="text-xs text-slate-500 dark:text-[#8B949E] mt-1">管理 Agent 可用的技能模块，启用或禁用特定 Skill</p>
      </div>
      <div class="flex items-center gap-2">
        <el-tooltip content="后端上传接口当前为占位，暂不可用" placement="top">
          <span>
            <el-button
              type="default"
              :icon="Upload"
              disabled
              class="!border-[#D0D7DE] dark:!border-[#30363D] !bg-white dark:!bg-[#161B22]"
            >
              上传
            </el-button>
          </span>
        </el-tooltip>
        <!-- 刷新按钮 -->
        <el-button
          type="primary"
          :icon="Refresh"
          :loading="loading"
          @click="loadSkills"
          class="!bg-[#0969DA] !border-[#0969DA] hover:!bg-[#0860CA]"
        >
          刷新
        </el-button>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading && skills.length === 0" class="flex items-center justify-center py-16">
      <el-icon class="is-loading text-2xl text-[#0969DA]"><Loading /></el-icon>
      <span class="ml-3 text-sm text-slate-500 dark:text-[#8B949E]">加载中…</span>
    </div>

    <!-- 空状态 -->
    <div
      v-else-if="!loading && skills.length === 0"
      class="text-center py-16 text-slate-400 dark:text-[#484F58]"
    >
      <el-icon class="text-4xl mb-3"><FolderOpened /></el-icon>
      <p class="text-sm">未检测到任何 Skill，请将 Skill 文件夹放置到 <code class="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-[#0D1117] text-xs">.skills/</code> 目录</p>
    </div>

    <!-- Skill 卡片列表 -->
    <div v-else class="grid gap-4">
      <div
        v-for="skill in skills"
        :key="skill.name"
        class="p-4 rounded-xl border transition-all duration-200"
        :class="skill.enabled
          ? 'border-[#0969DA]/30 dark:border-[#1F6FEB]/30 bg-white dark:bg-[#161B22]'
          : 'border-[#D0D7DE] dark:border-[#30363D] bg-slate-50/50 dark:bg-[#0D1117]/50 opacity-70'"
      >
        <div class="flex items-start justify-between gap-4">
          <!-- 左侧信息 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1.5">
              <!-- 状态指示灯 -->
              <span
                class="w-2 h-2 rounded-full flex-shrink-0"
                :class="skill.enabled ? 'bg-green-500' : 'bg-slate-300 dark:bg-[#484F58]'"
              />
              <h4 class="text-sm font-semibold text-slate-900 dark:text-[#C9D1D9] truncate">
                {{ skill.name }}
              </h4>
              <!-- 脚本数量标签 -->
              <span
                v-if="skill.has_scripts"
                class="text-[10px] font-mono px-2 py-0.5 rounded-full border border-[#D0D7DE] dark:border-[#30363D] text-slate-500 dark:text-[#8B949E] bg-slate-50 dark:bg-[#0D1117] flex-shrink-0"
              >
                {{ skill.scripts.length }} 脚本
              </span>
            </div>

            <p class="text-xs text-slate-500 dark:text-[#8B949E] leading-relaxed line-clamp-2">
              {{ skill.description || '暂无描述' }}
            </p>

            <!-- 脚本列表（可折叠） -->
            <div v-if="skill.has_scripts && expandedSkills.has(skill.name)" class="mt-3">
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="script in skill.scripts"
                  :key="script"
                  class="inline-flex items-center text-[11px] font-mono px-2 py-0.5 rounded-md bg-slate-100 dark:bg-[#0D1117] text-slate-600 dark:text-[#8B949E] border border-[#D0D7DE] dark:border-[#30363D]"
                >
                  <el-icon class="mr-1 text-[10px]"><Document /></el-icon>
                  {{ script }}
                </span>
              </div>
            </div>

            <!-- 展开/收起按钮 -->
            <button
              v-if="skill.has_scripts"
              type="button"
              @click="toggleExpand(skill.name)"
              class="mt-2 text-[11px] text-[#0969DA] dark:text-[#58A6FF] hover:underline focus:outline-none"
            >
              {{ expandedSkills.has(skill.name) ? '收起脚本' : `查看 ${skill.scripts.length} 个脚本` }}
            </button>
          </div>

          <!-- 右侧开关 -->
          <div class="flex-shrink-0 pt-0.5">
            <el-switch
              :model-value="skill.enabled"
              :loading="togglingSkill === skill.name"
              @change="(val: boolean) => handleToggle(skill.name, val)"
              active-color="#0969DA"
              :active-text="skill.enabled ? '已启用' : ''"
              :inactive-text="!skill.enabled ? '已禁用' : ''"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 未来规划：Agent Team Skill 分配 -->
    <div class="p-4 rounded-xl border border-dashed border-[#D0D7DE] dark:border-[#30363D] bg-slate-50/50 dark:bg-[#0D1117]/30">
      <div class="flex items-center gap-2 mb-2">
        <el-icon class="text-amber-500"><WarningFilled /></el-icon>
        <span class="text-xs font-semibold text-slate-600 dark:text-[#8B949E]">未来规划</span>
      </div>
      <p class="text-xs text-slate-500 dark:text-[#8B949E] leading-relaxed">
        启用 Agent Team 架构后，此页面将支持为不同 Agent 成员分配不同的 Skill 组合。
        例如：情报分析 Agent 仅携带 <code class="px-1 py-0.5 rounded bg-slate-100 dark:bg-[#0D1117] text-[10px]">threat-trace-skill</code>，
        处置执行 Agent 仅携带 <code class="px-1 py-0.5 rounded bg-slate-100 dark:bg-[#0D1117] text-[10px]">playbook-skill</code>。
      </p>
    </div>

    <!-- 提示 -->
    <div class="text-xs text-slate-400 dark:text-[#484F58] p-3 rounded-lg bg-slate-50 dark:bg-[#0D1117] border border-[#D0D7DE] dark:border-[#30363D]">
      注意：Skill 启用/禁用在下一次 Agent 对话时生效。每个 Skill 由 SKILL.md（SOP 描述）和 scripts/（可执行脚本）组成。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { Upload, Refresh, Loading, FolderOpened, Document, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useSkillsApi } from '../composables/useApi'
import type { SkillInfo } from '../types'

const { loading, fetchSkills: apiFetchSkills, toggleSkill: apiToggleSkill } = useSkillsApi()

const skills = ref<SkillInfo[]>([])
const togglingSkill = ref<string | null>(null)
const expandedSkills = reactive(new Set<string>())

const loadSkills = async () => {
  try {
    const data = await apiFetchSkills()
    skills.value = data.skills
  } catch {
    ElMessage.error('加载 Skills 列表失败')
  }
}

const handleToggle = async (name: string, enabled: boolean) => {
  togglingSkill.value = name
  try {
    await apiToggleSkill(name, enabled)
    // 更新本地状态
    const skill = skills.value.find(s => s.name === name)
    if (skill) skill.enabled = enabled
    ElMessage.success(`${name} 已${enabled ? '启用' : '禁用'}`)
  } catch {
    ElMessage.error('切换 Skill 状态失败')
  } finally {
    togglingSkill.value = null
  }
}

const toggleExpand = (name: string) => {
  if (expandedSkills.has(name)) {
    expandedSkills.delete(name)
  } else {
    expandedSkills.add(name)
  }
}

onMounted(() => {
  loadSkills()
})
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
