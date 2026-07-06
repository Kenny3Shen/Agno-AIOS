<template>
  <div class="skills-console ag-page-flow">
    <section class="skill-summary-strip ag-stat-strip">
      <span v-for="metric in summaryMetrics" :key="metric.label" class="skill-summary-chip ag-stat-chip">
        <small>{{ metric.label }}</small>
        <strong>{{ metric.value }}</strong>
      </span>
      <el-button
        :icon="Document"
        type="primary"
        class="skill-summary-action"
        :disabled="!canWriteSkills"
        @click="uploadPanelOpen = !uploadPanelOpen"
      >
        {{ t('skills.actions.upload') }}
      </el-button>
    </section>

    <main class="skills-main">
      <section class="skills-body">
        <section v-if="uploadPanelOpen" class="skill-upload-panel ag-content-panel">
          <div class="skill-card-head">
            <span class="skill-card-copy">
              <strong>{{ t('skills.upload.title') }}</strong>
              <em>{{ t('skills.upload.description') }}</em>
            </span>
          </div>
          <div class="skill-upload-grid">
            <el-input v-model="uploadForm.name" :placeholder="t('skills.upload.namePlaceholder')" />
            <el-upload
              ref="skillUploadRef"
              v-model:file-list="skillFileList"
              drag
              :auto-upload="false"
              :limit="1"
              accept=".zip,application/zip,application/x-zip-compressed"
              :on-change="handleSkillFileChange"
              :on-remove="handleSkillFileRemove"
              :on-exceed="handleSkillFileExceed"
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">
                {{ t('skills.upload.dropText') }} <em>{{ t('skills.upload.chooseFile') }}</em>
              </div>
              <template #tip>
                <div class="el-upload__tip">{{ t('skills.upload.supportedTypes') }}</div>
              </template>
            </el-upload>
          </div>
          <div class="skill-upload-actions">
            <el-button :disabled="submittingUpload" @click="cancelSkillUpload">
              {{ t('skills.upload.cancel') }}
            </el-button>
            <el-button type="primary" :loading="submittingUpload" @click="submitSkillUpload">
              {{ t('skills.upload.submit') }}
            </el-button>
          </div>
        </section>

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
import { ArrowDown, ArrowUp, Loading, FolderOpened, Document, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadFiles, UploadInstance, UploadUserFile } from 'element-plus'
import { useSkillsApi } from '../composables/useApi'
import { useAuthStore } from '../stores/auth'
import type { SkillInfo } from '../types'

const {
  loading,
  fetchSkills: apiFetchSkills,
  toggleSkill: apiToggleSkill,
  uploadSkill,
} = useSkillsApi()
const { t } = useI18n()
const authStore = useAuthStore()

const skills = ref<SkillInfo[]>([])
const togglingSkill = ref<string | null>(null)
const expandedSkills = reactive(new Set<string>())
const uploadPanelOpen = ref(false)
const submittingUpload = ref(false)
const skillUploadRef = ref<UploadInstance>()
const skillFileList = ref<UploadUserFile[]>([])
const selectedSkillArchive = ref<File | null>(null)
const uploadForm = reactive({
  name: "",
})
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

const stripZipExtension = (filename: string) => filename.replace(/\.zip$/i, "")

const handleSkillFileChange = (uploadFile: UploadFile, uploadFiles: UploadFiles) => {
  skillFileList.value = uploadFiles.slice(-1)
  selectedSkillArchive.value = uploadFile.raw ?? null
  if (!uploadForm.name && uploadFile.name) {
    uploadForm.name = stripZipExtension(uploadFile.name)
  }
}

const handleSkillFileRemove = () => {
  selectedSkillArchive.value = null
}

const handleSkillFileExceed = () => {
  ElMessage.warning(t("skills.messages.singleFileOnly"))
}

const resetSkillUpload = () => {
  uploadForm.name = ""
  selectedSkillArchive.value = null
  skillFileList.value = []
  skillUploadRef.value?.clearFiles()
}

const cancelSkillUpload = () => {
  resetSkillUpload()
  uploadPanelOpen.value = false
}

const submitSkillUpload = async () => {
  if (!uploadForm.name.trim()) {
    ElMessage.warning(t("skills.messages.uploadNameRequired"))
    return
  }
  if (!selectedSkillArchive.value) {
    ElMessage.warning(t("skills.messages.uploadFileRequired"))
    return
  }
  submittingUpload.value = true
  try {
    await uploadSkill({
      name: uploadForm.name.trim(),
      file: selectedSkillArchive.value,
    })
    resetSkillUpload()
    uploadPanelOpen.value = false
    await loadSkills()
    ElMessage.success(t("skills.messages.uploadSubmitted"))
  } catch {
    ElMessage.error(t("skills.messages.uploadFailed"))
  } finally {
    submittingUpload.value = false
  }
}

onMounted(() => {
  loadSkills()
})
</script>

<style scoped>
.skills-console {
  font-family: "Fira Sans", "Microsoft YaHei", sans-serif;
}

.skills-console :where(button, div, section, article, span, strong, small, em, code) {
  min-width: 0;
}

.skills-main {
  display: flex;
  flex-direction: column;
  gap: var(--ag-section-gap);
}

.skill-summary-strip {
  flex-wrap: wrap;
  flex-shrink: 0;
  block-size: auto;
  min-height: var(--ag-stat-strip-height);
}

.skill-summary-action {
  margin-left: auto;
}

.skills-body {
  display: grid;
  gap: var(--ag-section-gap);
}

.skill-upload-panel {
  display: grid;
  gap: 12px;
}

.skill-upload-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.skill-upload-grid :deep(.el-textarea) {
  grid-column: 1 / -1;
}

.skill-upload-actions {
  display: flex;
  justify-content: flex-end;
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
  min-height: 240px;
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
  .skill-summary-strip {
    display: grid;
    grid-template-columns: 1fr;
    align-items: stretch;
    overflow: visible;
  }

  .skill-summary-chip,
  .skill-summary-action {
    width: 100%;
  }

  .skill-summary-action {
    margin-left: 0;
  }

  .skills-grid {
    grid-template-columns: 1fr;
  }

  .skill-card-head {
    align-items: flex-start;
  }
}
</style>
