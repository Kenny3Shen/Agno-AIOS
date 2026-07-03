<template>
  <div class="skills-console">
    <main class="skills-main">
      <header class="skills-header">
        <div class="skill-summary-strip">
          <span v-for="metric in summaryMetrics" :key="metric.label" class="skill-summary-chip">
            <small>{{ metric.label }}</small>
            <strong>{{ metric.value }}</strong>
          </span>
        </div>

        <el-button
          type="primary"
          :icon="Refresh"
          :loading="loading"
          @click="loadSkills"
          class="skill-primary-action"
        >
          {{ t('skills.actions.refresh') }}
        </el-button>
      </header>

      <section class="skills-body">
        <div v-if="loading && skills.length === 0" class="skills-state">
          <el-icon class="skill-loading is-loading"><Loading /></el-icon>
          <span>{{ t('skills.loading') }}</span>
        </div>

        <div v-else-if="!loading && skills.length === 0" class="skills-state">
          <el-icon><FolderOpened /></el-icon>
          <span>
            {{ t('skills.empty.noSkillsPrefix') }}
            <code class="skill-code">api/agent/skills/</code>
            {{ t('skills.empty.noSkillsSuffix') }}
          </span>
        </div>

        <div v-else class="skills-grid">
          <article
            v-for="skill in skills"
            :key="skill.name"
            class="skill-card"
            :class="{ 'is-disabled': !skill.enabled, 'is-enabled': skill.enabled }"
          >
            <div class="skill-card-head">
              <div class="skill-card-main">
                <span class="skill-card-copy">
                  <strong :title="skill.name">{{ skill.name }}</strong>
                  <em>{{ skill.description || t('skills.empty.description') }}</em>
                </span>
              </div>
              <span class="status-pill" :class="skill.enabled ? 'ok' : 'off'">
                {{ skill.enabled ? t('common.state.enabled') : t('common.state.disabled') }}
              </span>
            </div>

            <div class="skill-card-foot">
              <button
                v-if="skill.has_scripts"
                type="button"
                class="skill-script-toggle"
                :aria-expanded="expandedSkills.has(skill.name)"
                :aria-label="
                  expandedSkills.has(skill.name)
                    ? t('skills.scripts.collapse')
                    : t('skills.scripts.expand', { count: skill.scripts.length })
                "
                @click="toggleExpand(skill.name)"
              >
                <span>{{ t('skills.scripts.count', { count: skill.scripts.length }) }}</span>
                <el-icon>
                  <ArrowUp v-if="expandedSkills.has(skill.name)" />
                  <ArrowDown v-else />
                </el-icon>
              </button>
              <span v-else class="skill-script-empty">{{ t('skills.scripts.count', { count: 0 }) }}</span>

              <el-switch
                :model-value="skill.enabled"
                :loading="togglingSkill === skill.name"
                :disabled="!canWriteSkills"
                active-color="var(--ag-blue)"
                @change="(val: string | number | boolean) => handleToggle(skill.name, Boolean(val))"
              />
            </div>

            <div v-if="skill.has_scripts && expandedSkills.has(skill.name)" class="skill-script-list">
              <div>
                <span
                  v-for="script in skill.scripts"
                  :key="script"
                  class="skill-script-pill"
                >
                  <el-icon><Document /></el-icon>
                  {{ script }}
                </span>
              </div>
            </div>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, Refresh, Loading, FolderOpened, Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useSkillsApi } from '../composables/useApi'
import { useAuthStore } from '../stores/auth'
import type { SkillInfo } from '../types'

const { loading, fetchSkills: apiFetchSkills, toggleSkill: apiToggleSkill } = useSkillsApi()
const { t } = useI18n()
const authStore = useAuthStore()

const skills = ref<SkillInfo[]>([])
const togglingSkill = ref<string | null>(null)
const expandedSkills = reactive(new Set<string>())
const canWriteSkills = computed(() => authStore.hasPermission("skill:write"))
const enabledSkills = computed(() => skills.value.filter((skill) => skill.enabled).length)
const totalScripts = computed(() => skills.value.reduce((sum, skill) => sum + skill.scripts.length, 0))
const summaryMetrics = computed(() => [
  { label: t('skills.summary.total'), value: skills.value.length },
  { label: t('skills.summary.enabled'), value: enabledSkills.value },
  { label: t('skills.summary.scripts'), value: totalScripts.value },
])

const loadSkills = async () => {
  try {
    const data = await apiFetchSkills()
    skills.value = data.skills
  } catch {
    ElMessage.error(t('skills.messages.loadFailed'))
  }
}

const handleToggle = async (name: string, enabled: boolean) => {
  if (!canWriteSkills.value) return
  togglingSkill.value = name
  try {
    await apiToggleSkill(name, enabled)
    const skill = skills.value.find(s => s.name === name)
    if (skill) skill.enabled = enabled
    ElMessage.success(t('skills.messages.toggled', {
      name,
      state: t(enabled ? 'skills.state.enabledAction' : 'skills.state.disabledAction'),
    }))
  } catch {
    ElMessage.error(t('skills.messages.toggleFailed'))
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
.skills-console {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--ag-panel-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel-soft);
  padding: 0;
  color: var(--ag-text);
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
}

.skills-console :where(button, div, section, article, span, strong, small, em, code) {
  min-width: 0;
}

.skills-main {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
  border-radius: inherit;
}

.skills-header {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--ag-panel-border);
  background: var(--ag-panel-bg);
  padding: 12px;
}

.skill-summary-strip {
  display: flex;
  flex: 1 1 520px;
  flex-wrap: wrap;
  gap: 8px;
}

.skill-summary-chip {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--ag-border);
  border-radius: 999px;
  background: var(--ag-panel-soft);
  padding: 6px 10px;
}

.skill-summary-chip small {
  color: var(--ag-muted);
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}

.skill-summary-chip strong {
  color: var(--ag-heading);
  font-family: "Fira Code", "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 700;
}

.skill-primary-action {
  --el-button-bg-color: var(--ag-blue);
  --el-button-border-color: var(--ag-blue);
  --el-button-hover-bg-color: color-mix(in srgb, var(--ag-blue) 86%, var(--ag-heading));
  --el-button-hover-border-color: color-mix(in srgb, var(--ag-blue) 86%, var(--ag-heading));
}

.skills-body {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.skills-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}

.skill-card {
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel);
  padding: 12px;
  transition:
    border-color 0.18s ease,
    background 0.18s ease;
}

.skill-card.is-disabled {
  opacity: 0.72;
}

.skill-card-head,
.skill-card-foot,
.skill-card-main,
.skill-script-toggle,
.skill-script-empty,
.skill-script-pill {
  display: flex;
  align-items: center;
}

.skill-card-head {
  justify-content: space-between;
  gap: 12px;
}

.skill-card-main {
  min-width: 0;
  align-items: flex-start;
}

.skill-card-copy {
  min-width: 0;
}

.skill-card-copy strong {
  display: block;
  overflow: hidden;
  color: var(--ag-heading);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-card-copy em {
  display: -webkit-box;
  margin-top: 3px;
  overflow: hidden;
  color: var(--ag-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.status-pill {
  flex: 0 0 auto;
}

.skill-card-foot {
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
}

.skill-script-toggle,
.skill-script-empty {
  min-height: 24px;
  gap: 6px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  padding: 3px 7px;
  color: var(--ag-muted-strong);
  font-family: "Fira Code", "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 700;
}

.skill-script-toggle:hover,
.skill-script-toggle:focus-visible {
  border-color: color-mix(in srgb, var(--ag-blue) 42%, var(--ag-border));
  color: var(--ag-blue);
}

.skill-script-toggle:focus-visible {
  outline: 2px solid var(--ag-blue);
  outline-offset: 2px;
}

.skills-console :deep(.el-switch) {
  flex: 0 0 auto;
}

.skills-console :deep(.el-switch__core) {
  min-width: 40px;
}

.skill-script-pill,
.skill-code {
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  color: var(--ag-muted-strong);
}

.skill-script-list {
  margin-top: 12px;
  border-top: 1px solid var(--ag-border);
  padding-top: 12px;
}

.skill-script-list > div {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.skill-script-pill {
  max-width: 100%;
  gap: 4px;
  padding: 3px 7px;
  overflow-wrap: anywhere;
  font-family: "Fira Code", "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 650;
  line-height: 1.35;
}

.skill-code {
  padding: 2px 6px;
  font-family: "Fira Code", "JetBrains Mono", monospace;
  font-size: 11px;
}

.skills-state {
  display: grid;
  min-height: 300px;
  place-items: center;
  align-content: center;
  gap: 10px;
  border: 1px dashed var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-panel);
  padding: 32px;
  color: var(--ag-muted);
  font-size: 12px;
  text-align: center;
}

.skills-state .el-icon {
  color: var(--ag-blue);
  font-size: 28px;
}

.skill-loading {
  color: var(--ag-blue);
}

@media (max-width: 760px) {
  .skills-header,
  .skills-body {
    padding: 10px;
  }

  .skills-grid {
    grid-template-columns: 1fr;
  }

  .skill-card-head {
    align-items: flex-start;
  }
}
</style>
