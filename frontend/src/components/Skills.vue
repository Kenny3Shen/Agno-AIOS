<template>
  <div class="skills-console ag-page-flow">
    <section class="skill-toolbar ag-content-panel">
      <div class="skill-context">
        <span v-for="metric in summaryMetrics" :key="metric.label" class="skill-context-chip">
          <small>{{ metric.label }}</small>
          <strong>{{ metric.value }}</strong>
        </span>
      </div>
      <el-button
        :icon="Document"
        type="primary"
        class="skill-toolbar-action"
        :disabled="!canWriteSkills"
        @click="uploadPanelOpen = !uploadPanelOpen"
      >
        {{ t('skills.actions.upload') }}
      </el-button>
    </section>

    <main class="skills-main">
      <section class="skills-body">
        <section v-if="uploadPanelOpen" class="skill-upload-panel ag-content-panel">
          <div class="skill-upload-head">
            <span class="skill-upload-copy">
              <strong>{{ t('skills.upload.title') }}</strong>
              <em>{{ t('skills.upload.description') }}</em>
            </span>
          </div>
          <div class="skill-upload-grid">
            <el-input v-model="uploadForm.name" :placeholder="t('skills.upload.namePlaceholder')" />
            <label class="skill-visibility-field">
              <span>{{ t('visibility.label') }}</span>
              <ResourceVisibilityTabs v-model="uploadForm.visibility" />
            </label>
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

        <section
          v-else
          class="skill-workbench"
          :class="{ 'is-resizing': isResizingSkillList }"
          :style="skillWorkbenchStyle"
        >
          <aside class="skill-list-panel ag-content-panel" :aria-label="t('skills.list.title')">
            <div class="skill-list-head">
              <span>{{ t('skills.list.title') }}</span>
              <strong>{{ skills.length }}</strong>
            </div>
            <div class="skill-list">
              <button
                v-for="skill in skills"
                :key="skill.name"
                type="button"
                class="skill-list-item"
                :class="{ 'is-selected': selectedSkillName === skill.name, 'is-disabled': !skill.enabled }"
                :aria-pressed="selectedSkillName === skill.name"
                @click="selectedSkillName = skill.name"
              >
                <span class="skill-list-copy">
                  <strong :title="skill.name">{{ skill.name }}</strong>
                  <em>{{ skill.description || t('skills.empty.description') }}</em>
                </span>
                <span class="skill-list-meta">
                  <span class="skill-state-pill" :class="skill.enabled ? 'ok' : 'off'">
                    {{ skill.enabled ? t('common.state.enabled') : t('common.state.disabled') }}
                  </span>
                  <span class="skill-script-count">{{ t('skills.scripts.count', { count: skill.scripts.length }) }}</span>
                </span>
              </button>
            </div>
          </aside>

          <button
            type="button"
            class="skill-resize-handle"
            :aria-label="t('skills.resize.label')"
            @pointerdown="startSkillResize"
            @keydown.left.prevent="adjustSkillListWidth(-2)"
            @keydown.right.prevent="adjustSkillListWidth(2)"
          >
            <span></span>
          </button>

          <section v-if="selectedSkill" class="skill-detail-panel ag-content-panel">
            <header class="skill-detail-header">
              <div class="skill-detail-title">
                <span>{{ t('skills.detail.fileLabel') }}</span>
                <h2 :title="selectedSkill.name">{{ selectedSkill.name }}</h2>
              </div>
              <div class="skill-detail-actions">
                <el-switch
                  :model-value="selectedSkill.enabled"
                  :loading="togglingSkill === selectedSkill.name"
                  :disabled="!canWriteSkills || !selectedSkill.can_manage"
                  active-color="var(--ag-blue)"
                  @change="(val: string | number | boolean) => handleToggle(selectedSkill.name, Boolean(val))"
                />
                <ResourceVisibilityTabs
                  :model-value="selectedSkill.visibility"
                  :aria-label="t('skills.visibilityLabel', { name: selectedSkill.name })"
                  :disabled="!canWriteSkills || !selectedSkill.can_manage"
                  :loading="togglingSkill === selectedSkill.name"
                  @update:model-value="(visibility) => handleVisibilityChange(selectedSkill, visibility)"
                />
              </div>
            </header>

            <p class="skill-detail-description">
              {{ selectedSkill.description || t('skills.empty.description') }}
            </p>

            <el-tabs v-model="activeSkillDetailTab" class="skill-detail-tabs">
              <el-tab-pane :label="t('skills.tabs.metadata')" name="metadata">
                <div class="skill-metadata-shell">
                  <span class="skill-frontmatter-marker">---</span>
                  <dl class="skill-metadata-grid">
                    <div v-for="item in selectedSkillMetadata" :key="item.label" class="skill-metadata-row">
                      <dt>{{ item.label }}</dt>
                      <dd>{{ item.value }}</dd>
                    </div>
                  </dl>
                  <span class="skill-frontmatter-marker">---</span>
                </div>

                <div class="skill-script-list">
                  <span class="skill-section-label">{{ t('skills.scripts.title') }}</span>
                  <span
                    v-for="script in selectedSkill.scripts"
                    :key="script"
                    class="skill-script-pill"
                  >
                    <el-icon><Document /></el-icon>
                    {{ script }}
                  </span>
                  <span v-if="selectedSkill.scripts.length === 0" class="skill-script-empty">
                    {{ t('skills.scripts.none') }}
                  </span>
                </div>
              </el-tab-pane>
              <el-tab-pane :label="t('skills.tabs.detail')" name="detail">
                <div class="skill-detail-source" v-html="renderSelectedSkillMarkdown()"></div>
              </el-tab-pane>
            </el-tabs>
          </section>
        </section>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Loading, FolderOpened, Document, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import MarkdownIt from "markdown-it"
import type { UploadFile, UploadFiles, UploadInstance, UploadUserFile } from 'element-plus'
import { useSkillsApi } from '../composables/useApi'
import { useAuthStore } from '../stores/auth'
import type { ResourceVisibility, SkillInfo } from '../types'
import ResourceVisibilityTabs from "./common/ResourceVisibilityTabs.vue"

const {
  loading,
  fetchSkills: apiFetchSkills,
  toggleSkill: apiToggleSkill,
  uploadSkill,
  updateSkillVisibility,
} = useSkillsApi()
const { t } = useI18n()
const authStore = useAuthStore()
const skillMarkdownRenderer = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const skills = ref<SkillInfo[]>([])
const selectedSkillName = ref("")
const activeSkillDetailTab = ref<"metadata" | "detail">("metadata")
const skillListWidth = ref(20)
const isResizingSkillList = ref(false)
const togglingSkill = ref<string | null>(null)
const uploadPanelOpen = ref(false)
const submittingUpload = ref(false)
const skillUploadRef = ref<UploadInstance>()
const skillFileList = ref<UploadUserFile[]>([])
const selectedSkillArchive = ref<File | null>(null)
const uploadForm = reactive({
  name: "",
  visibility: "private" as ResourceVisibility,
})
const canWriteSkills = computed(() => authStore.hasScope("skill:write"))
const enabledSkills = computed(() => skills.value.filter((skill) => skill.enabled).length)
const totalScripts = computed(() => skills.value.reduce((sum, skill) => sum + skill.scripts.length, 0))
const summaryMetrics = computed(() => [
  { label: t('skills.summary.total'), value: skills.value.length },
  { label: t('skills.summary.enabled'), value: enabledSkills.value },
  { label: t('skills.summary.scripts'), value: totalScripts.value },
])
const skillWorkbenchStyle = computed(() => ({
  "--skill-list-width": `${skillListWidth.value}%`,
}))
const selectedSkill = computed(() => skills.value.find((skill) => skill.name === selectedSkillName.value) ?? skills.value[0] ?? null)
const selectedSkillMetadata = computed(() => {
  const skill = selectedSkill.value
  if (!skill) return []
  return [
    { label: t("skills.metadata.name"), value: skill.name },
    { label: t("skills.metadata.description"), value: skill.description || t("skills.empty.description") },
    { label: t("skills.metadata.enabled"), value: skill.enabled ? t("common.state.enabled") : t("common.state.disabled") },
    { label: t("skills.metadata.visibility"), value: t(`visibility.${skill.visibility}`) },
    { label: t("skills.metadata.owner"), value: skill.owner_user_id || "-" },
    { label: t("skills.metadata.manageable"), value: skill.can_manage ? t("common.state.enabled") : t("common.state.disabled") },
    { label: t("skills.metadata.scripts"), value: String(skill.scripts.length) },
  ]
})

const formatSkillMarkdownForRender = (markdown: string) => {
  const normalized = markdown.trim()
  if (!/^---\r?\n/.test(normalized)) return normalized

  const lines = normalized.split(/\r?\n/)
  const closingIndex = lines.findIndex((line, index) => index > 0 && line.trim() === "---")
  if (closingIndex === -1) return normalized

  const frontmatter = lines.slice(1, closingIndex).join("\n").trim()
  const body = lines.slice(closingIndex + 1).join("\n").trim()
  return ["```yaml", frontmatter, "```", body].filter(Boolean).join("\n\n")
}

const renderSelectedSkillMarkdown = () => {
  const markdown = selectedSkill.value?.skill_markdown?.trim() || t("skills.detail.empty")
  return skillMarkdownRenderer.render(formatSkillMarkdownForRender(markdown))
}

const clampSkillListWidth = (value: number) => Math.min(42, Math.max(16, value))

const adjustSkillListWidth = (delta: number) => {
  skillListWidth.value = clampSkillListWidth(skillListWidth.value + delta)
}

const startSkillResize = (event: PointerEvent) => {
  if (window.matchMedia("(max-width: 760px)").matches) return
  const workbench = (event.currentTarget as HTMLElement).closest(".skill-workbench")
  if (!(workbench instanceof HTMLElement)) return
  const rect = workbench.getBoundingClientRect()
  if (rect.width <= 0) return

  const updateWidth = (clientX: number) => {
    skillListWidth.value = clampSkillListWidth(((clientX - rect.left) / rect.width) * 100)
  }
  const handleMove = (moveEvent: PointerEvent) => updateWidth(moveEvent.clientX)
  const stopResize = () => {
    isResizingSkillList.value = false
    window.removeEventListener("pointermove", handleMove)
    window.removeEventListener("pointerup", stopResize)
    window.removeEventListener("pointercancel", stopResize)
  }

  isResizingSkillList.value = true
  updateWidth(event.clientX)
  window.addEventListener("pointermove", handleMove)
  window.addEventListener("pointerup", stopResize, { once: true })
  window.addEventListener("pointercancel", stopResize, { once: true })
  event.preventDefault()
}

const loadSkills = async () => {
  try {
    const data = await apiFetchSkills()
    skills.value = data.skills
    if (!skills.value.some((skill) => skill.name === selectedSkillName.value)) {
      selectedSkillName.value = skills.value[0]?.name ?? ""
    }
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
  uploadForm.visibility = "private"
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
      visibility: uploadForm.visibility,
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

const handleVisibilityChange = async (skill: SkillInfo, visibility: ResourceVisibility) => {
  if (!canWriteSkills.value || !skill.can_manage) return
  if (visibility === skill.visibility) return
  togglingSkill.value = skill.name
  try {
    const result = await updateSkillVisibility(skill.name, visibility)
    skill.visibility = result.visibility
    await loadSkills()
    ElMessage.success(t("visibility.updated"))
  } catch {
    ElMessage.error(t("visibility.updateFailed"))
  } finally {
    togglingSkill.value = null
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

.skill-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.skill-context {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 8px;
}

.skill-context-chip {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  padding: 6px 9px;
}

.skill-context-chip small,
.skill-context-chip strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-context-chip small {
  color: var(--ag-muted);
  font-size: 11px;
  font-weight: 720;
}

.skill-context-chip strong {
  color: var(--ag-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
}

.skill-toolbar-action {
  flex: 0 0 auto;
}

.skills-body {
  display: grid;
  gap: var(--ag-section-gap);
}

.skill-upload-panel {
  display: grid;
  gap: 12px;
}

.skill-upload-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.skill-upload-copy {
  min-width: 0;
}

.skill-upload-copy strong {
  display: block;
  overflow: hidden;
  color: var(--ag-heading);
  font-size: 13px;
  font-weight: 760;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-upload-copy em {
  display: block;
  margin-top: 3px;
  overflow: hidden;
  color: var(--ag-muted);
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-upload-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.skill-visibility-field {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.skill-visibility-field > span {
  color: var(--ag-muted);
  font-size: 12px;
  font-weight: 700;
}

.skill-upload-grid :deep(.el-textarea) {
  grid-column: 1 / -1;
}

.skill-upload-actions {
  display: flex;
  justify-content: flex-end;
}

.skill-workbench {
  display: grid;
  min-height: 520px;
  gap: 8px;
  grid-template-columns: minmax(180px, var(--skill-list-width, 20%)) 8px minmax(0, 1fr);
}

.skill-workbench.is-resizing {
  cursor: col-resize;
  user-select: none;
}

.skill-list-panel,
.skill-detail-panel {
  min-height: 0;
}

.skill-list-panel {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 10px;
}

.skill-resize-handle {
  display: grid;
  width: 8px;
  min-height: 100%;
  place-items: center;
  border: 0;
  border-radius: var(--ag-radius-control);
  background: transparent;
  cursor: col-resize;
}

.skill-resize-handle span {
  display: block;
  width: 2px;
  height: 64px;
  border-radius: var(--ag-radius-control);
  background: color-mix(in srgb, var(--ag-border) 72%, transparent);
  transition:
    background 0.18s ease,
    height 0.18s ease;
}

.skill-resize-handle:hover span,
.skill-resize-handle:focus-visible span,
.skill-workbench.is-resizing .skill-resize-handle span {
  height: 88px;
  background: color-mix(in srgb, var(--ag-blue) 64%, var(--ag-border));
}

.skill-resize-handle:focus-visible {
  outline: 2px solid var(--ag-blue);
  outline-offset: 2px;
}

.skill-list-head,
.skill-list-item,
.skill-list-meta,
.skill-detail-header,
.skill-detail-actions,
.skill-state-pill,
.skill-script-pill,
.skill-script-empty {
  display: flex;
  align-items: center;
}

.skill-list-head {
  justify-content: space-between;
  gap: 10px;
  padding: 2px 2px 6px;
  color: var(--ag-muted);
  font-size: 11px;
  font-weight: 760;
  text-transform: uppercase;
}

.skill-list-head strong {
  color: var(--ag-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
}

.skill-list {
  display: grid;
  gap: 6px;
  max-height: min(62vh, 620px);
  overflow: auto;
  padding-right: 2px;
}

.skill-list-item {
  width: 100%;
  min-height: 78px;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid transparent;
  border-radius: var(--ag-radius-control);
  background: transparent;
  padding: 10px;
  text-align: left;
  transition:
    border-color 0.18s ease,
    background 0.18s ease,
    transform 0.18s ease;
}

.skill-list-item:hover,
.skill-list-item:focus-visible {
  border-color: color-mix(in srgb, var(--ag-blue) 42%, var(--ag-border));
  background: var(--ag-panel-soft);
}

.skill-list-item:focus-visible {
  outline: 2px solid var(--ag-blue);
  outline-offset: 2px;
}

.skill-list-item.is-selected {
  border-color: color-mix(in srgb, var(--ag-blue) 58%, var(--ag-border));
  background: color-mix(in srgb, var(--ag-blue) 9%, var(--ag-panel));
}

.skill-list-item.is-disabled {
  opacity: 0.72;
}

.skill-list-copy {
  min-width: 0;
  flex: 1 1 auto;
}

.skill-list-copy strong {
  display: -webkit-box;
  overflow: hidden;
  color: var(--ag-heading);
  font-size: 12px;
  font-weight: 760;
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
}

.skill-list-copy em {
  display: -webkit-box;
  margin-top: 4px;
  overflow: hidden;
  color: var(--ag-muted);
  font-size: 11px;
  font-style: normal;
  line-height: 1.45;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.skill-list-meta {
  flex: 0 0 auto;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.skill-state-pill {
  width: 44px;
  min-height: 24px;
  justify-content: center;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  color: var(--ag-muted-strong);
  font-size: 12px;
  font-weight: 760;
  line-height: 1;
  white-space: nowrap;
}

.skill-state-pill.ok {
  border-color: color-mix(in srgb, var(--ag-blue) 42%, var(--ag-border));
  color: var(--ag-heading);
}

.skill-state-pill.off {
  color: var(--ag-muted);
}

.skill-script-count,
.skill-script-empty {
  min-height: 24px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  padding: 3px 7px;
  color: var(--ag-muted-strong);
  font-family: "Fira Code", "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 700;
}

.skill-detail-panel {
  display: grid;
  align-content: start;
  gap: 16px;
  padding: 16px;
}

.skill-detail-header {
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--ag-border);
  padding-bottom: 14px;
}

.skill-detail-title {
  min-width: 0;
}

.skill-detail-title span {
  display: block;
  color: var(--ag-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 760;
  letter-spacing: 0;
}

.skill-section-label {
  display: block;
  color: var(--ag-muted);
  font-size: 11px;
  font-weight: 760;
  letter-spacing: 0;
  text-transform: uppercase;
}

.skill-detail-title h2 {
  margin: 4px 0 0;
  overflow: hidden;
  color: var(--ag-heading);
  font-size: clamp(18px, 2vw, 26px);
  font-weight: 780;
  line-height: 1.16;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-detail-actions {
  flex: 0 0 auto;
  justify-content: flex-end;
  gap: 10px;
}

.skill-detail-description {
  margin: 0;
  max-width: 820px;
  color: var(--ag-muted-strong);
  font-size: 13px;
  line-height: 1.6;
}

.skill-detail-tabs {
  min-width: 0;
}

.skill-detail-tabs :deep(.el-tabs__header) {
  margin-bottom: 14px;
}

.skill-detail-tabs :deep(.el-tabs__item) {
  font-size: 12px;
  font-weight: 760;
}

.skill-metadata-shell {
  display: grid;
  gap: 8px;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--ag-blue) 12%, transparent), transparent 26%),
    var(--ag-panel-soft);
  padding: 14px;
}

.skill-frontmatter-marker {
  color: var(--ag-muted);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 760;
}

.skill-metadata-grid {
  display: grid;
  gap: 1px;
  margin: 0;
  overflow: hidden;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-border);
}

.skill-metadata-row {
  display: grid;
  grid-template-columns: minmax(130px, 0.34fr) minmax(0, 0.66fr);
  gap: 12px;
  background: var(--ag-panel);
  padding: 9px 11px;
}

.skill-metadata-row dt,
.skill-metadata-row dd {
  margin: 0;
  min-width: 0;
}

.skill-metadata-row dt {
  color: var(--ag-muted);
  font-size: 11px;
  font-weight: 760;
}

.skill-metadata-row dd {
  overflow-wrap: anywhere;
  color: var(--ag-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  font-weight: 650;
  line-height: 1.45;
}

.skill-detail-source {
  max-height: min(58vh, 640px);
  margin: 0;
  overflow: auto;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--ag-green) 8%, transparent), transparent 32%),
    var(--ag-panel-soft);
  padding: 14px;
  color: var(--ag-muted-strong);
  font-size: 13px;
  font-weight: 560;
  line-height: 1.62;
}

.skill-detail-source :deep(*) {
  min-width: 0;
}

.skill-detail-source :deep(p),
.skill-detail-source :deep(ul),
.skill-detail-source :deep(ol),
.skill-detail-source :deep(pre),
.skill-detail-source :deep(blockquote) {
  margin: 0 0 10px;
}

.skill-detail-source :deep(h1),
.skill-detail-source :deep(h2),
.skill-detail-source :deep(h3) {
  margin: 14px 0 8px;
  color: var(--ag-heading);
  font-weight: 780;
  line-height: 1.25;
}

.skill-detail-source :deep(h1) {
  font-size: 18px;
}

.skill-detail-source :deep(h2) {
  font-size: 15px;
}

.skill-detail-source :deep(h3) {
  font-size: 13px;
}

.skill-detail-source :deep(ul),
.skill-detail-source :deep(ol) {
  padding-left: 20px;
}

.skill-detail-source :deep(li + li) {
  margin-top: 4px;
}

.skill-detail-source :deep(code) {
  border: 1px solid var(--ag-border);
  border-radius: 5px;
  background: var(--ag-panel);
  padding: 1px 5px;
  color: var(--ag-heading);
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
}

.skill-detail-source :deep(pre) {
  overflow: auto;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel);
  padding: 10px;
}

.skill-detail-source :deep(pre code) {
  border: 0;
  background: transparent;
  padding: 0;
}

.skill-detail-source :deep(a) {
  color: var(--ag-blue);
}

.skill-detail-source :deep(blockquote) {
  border-left: 3px solid var(--ag-border);
  padding-left: 10px;
  color: var(--ag-muted);
}

.skills-console :deep(.el-switch) {
  flex: 0 0 auto;
}

.skills-console :deep(.el-switch__core) {
  min-width: 40px;
}

.skill-script-pill,
.skill-script-count,
.skill-script-empty,
.skill-code {
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-control);
  background: var(--ag-panel-soft);
  color: var(--ag-muted-strong);
}

.skill-script-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-top: 1px solid var(--ag-border);
  padding-top: 14px;
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

.skill-script-empty {
  gap: 4px;
}

.skill-section-label {
  width: 100%;
  margin-bottom: 2px;
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
  .skill-toolbar {
    display: grid;
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .skill-context,
  .skill-toolbar-action {
    width: 100%;
  }

  .skill-context {
    display: grid;
  }

  .skill-upload-grid,
  .skill-workbench {
    grid-template-columns: 1fr;
  }

  .skill-workbench {
    min-height: 0;
  }

  .skill-resize-handle {
    display: none;
  }

  .skill-list {
    max-height: 360px;
  }

  .skill-detail-header,
  .skill-detail-actions {
    align-items: flex-start;
  }

  .skill-detail-header {
    display: grid;
  }

  .skill-detail-actions {
    justify-content: flex-start;
  }

  .skill-metadata-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
