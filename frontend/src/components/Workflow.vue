<template>
  <div class="workflow-console">
    <aside class="workflow-palette">
      <div class="workflow-head">
        <p>{{ t("workflow.palette.title") }}</p>
        <span>{{ t("workflow.palette.description") }}</span>
      </div>
      <button v-for="node in nodeTypes" :key="node.type" type="button" class="workflow-node-template">
        <span>{{ node.badge }}</span>
        <strong>{{ node.label }}</strong>
        <em>{{ node.description }}</em>
      </button>
    </aside>

    <main class="workflow-canvas">
      <header class="workflow-toolbar">
        <div>
          <p>{{ t("workflow.title") }}</p>
          <span>{{ t("workflow.description") }}</span>
        </div>
        <div class="workflow-actions">
          <el-button size="small" plain>{{ t("workflow.actions.validate") }}</el-button>
          <el-button size="small" type="primary">{{ t("workflow.actions.saveDraft") }}</el-button>
        </div>
      </header>

      <section class="workflow-board">
        <article v-for="(node, index) in starterNodes" :key="node.id" class="workflow-board-node" :class="`tone-${node.tone}`">
          <span class="workflow-step">{{ index + 1 }}</span>
          <div>
            <strong>{{ node.title }}</strong>
            <p>{{ node.description }}</p>
          </div>
        </article>
      </section>
    </main>

    <aside class="workflow-inspector">
      <div class="workflow-head">
        <p>{{ t("workflow.inspector.title") }}</p>
        <span>{{ t("workflow.inspector.description") }}</span>
      </div>
      <div class="workflow-inspector-grid">
        <span v-for="item in inspectorItems" :key="item.label">
          <small>{{ item.label }}</small>
          <strong>{{ item.value }}</strong>
        </span>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n"

const { t } = useI18n()

const nodeTypes = [
  { type: "trigger", badge: "TR", label: t("workflow.nodes.trigger"), description: t("workflow.nodes.triggerDescription") },
  { type: "agent", badge: "AG", label: t("workflow.nodes.agent"), description: t("workflow.nodes.agentDescription") },
  { type: "skill", badge: "SK", label: t("workflow.nodes.skill"), description: t("workflow.nodes.skillDescription") },
  { type: "approval", badge: "AP", label: t("workflow.nodes.approval"), description: t("workflow.nodes.approvalDescription") },
]

const starterNodes = [
  { id: "trigger", title: t("workflow.sample.trigger"), description: t("workflow.sample.triggerDescription"), tone: "blue" },
  { id: "enrich", title: t("workflow.sample.enrich"), description: t("workflow.sample.enrichDescription"), tone: "green" },
  { id: "approval", title: t("workflow.sample.approval"), description: t("workflow.sample.approvalDescription"), tone: "yellow" },
  { id: "action", title: t("workflow.sample.action"), description: t("workflow.sample.actionDescription"), tone: "red" },
]

const inspectorItems = [
  { label: t("workflow.inspector.mode"), value: t("workflow.inspector.lowCode") },
  { label: t("workflow.inspector.storage"), value: t("workflow.inspector.draft") },
  { label: t("workflow.inspector.runtime"), value: "Scheduler / Agent" },
]
</script>

<style scoped>
.workflow-console {
  display: grid;
  height: 100%;
  min-height: 0;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
  overflow: hidden;
  background: var(--ag-frame);
  color: var(--ag-text);
}

.workflow-palette,
.workflow-inspector,
.workflow-canvas {
  min-height: 0;
  overflow: auto;
}

.workflow-palette,
.workflow-inspector {
  border-right: 1px solid var(--ag-border);
  background: var(--ag-panel);
  padding: 14px;
}

.workflow-inspector {
  border-right: 0;
  border-left: 1px solid var(--ag-border);
}

.workflow-head p,
.workflow-toolbar p {
  margin: 0;
  color: var(--ag-muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.workflow-head span,
.workflow-toolbar span {
  display: block;
  margin-top: 4px;
  color: var(--ag-muted);
  font-size: 12px;
  line-height: 1.45;
}

.workflow-node-template,
.workflow-board-node,
.workflow-inspector-grid span {
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-panel-soft);
}

.workflow-node-template {
  display: grid;
  width: 100%;
  gap: 5px;
  margin-top: 10px;
  padding: 10px;
  text-align: left;
}

.workflow-node-template span,
.workflow-step {
  color: var(--ag-blue);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 800;
}

.workflow-node-template strong,
.workflow-board-node strong,
.workflow-inspector-grid strong {
  color: var(--ag-heading);
  font-size: 13px;
}

.workflow-node-template em,
.workflow-board-node p,
.workflow-inspector-grid small {
  color: var(--ag-muted);
  font-size: 12px;
  font-style: normal;
}

.workflow-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--ag-border);
  background: var(--ag-panel);
  padding: 14px;
}

.workflow-actions {
  display: flex;
  gap: 8px;
}

.workflow-board {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.workflow-board-node {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  align-items: start;
  gap: 12px;
  max-width: 720px;
  padding: 14px;
}

.workflow-step {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 1px solid var(--ag-border);
  border-radius: 8px;
  background: var(--ag-panel);
}

.workflow-inspector-grid {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.workflow-inspector-grid span {
  display: grid;
  gap: 4px;
  padding: 10px;
}

@media (max-width: 1100px) {
  .workflow-console {
    grid-template-columns: minmax(0, 1fr);
  }

  .workflow-palette,
  .workflow-inspector {
    display: none;
  }
}
</style>
