<template>
  <div class="ag-markdown-viewer min-w-0" v-html="renderedHtml" />
</template>

<script setup lang="ts">
import { computed } from "vue"
import MarkdownIt from "markdown-it"
import hljs from "highlight.js"

const props = withDefaults(defineProps<{
  content: string
}>(), {
  content: "",
})

const markdownRenderer: MarkdownIt = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: true,
  highlight: (value: string, language: string): string => {
    const safeLanguage = markdownRenderer.utils.escapeHtml(language || "")
    if (language && hljs.getLanguage(language)) {
      try {
        return `<pre class="hljs" data-lang="${safeLanguage}"><code class="language-${safeLanguage}">` +
          hljs.highlight(value, { language, ignoreIllegals: true }).value +
          "</code></pre>"
      } catch {
        return `<pre class="hljs" data-lang="${safeLanguage}"><code class="language-${safeLanguage}">` +
          markdownRenderer.utils.escapeHtml(value) +
          "</code></pre>"
      }
    }
    return `<pre class="hljs" data-lang="${safeLanguage}"><code class="language-${safeLanguage}">` +
      markdownRenderer.utils.escapeHtml(value) +
      "</code></pre>"
  },
})

const buildTableSeparator = (headerLine: string) => {
  const columns = headerLine.split("|").map((column) => column.trim()).filter(Boolean)
  return columns.length ? `| ${columns.map(() => "---").join(" | ")} |` : ""
}

const normalizeInlineTable = (content: string) => {
  if (!content.includes("||")) return content
  const lines = content.replace(/\|\|/g, "|\n|").split("\n")
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    if (!line || !line.trim().startsWith("|")) continue
    const nextLine = lines[index + 1] ?? ""
    if (!/^\s*\|?\s*:?[-]+:?\s*(\|\s*:?[-]+:?\s*)+\|?\s*$/.test(nextLine)) {
      const separator = buildTableSeparator(line)
      if (separator) lines.splice(index + 1, 0, separator)
    }
    break
  }
  return lines.join("\n")
}

const renderedHtml = computed(() => markdownRenderer.render(normalizeInlineTable(props.content || "")))
</script>

<style scoped>
.ag-markdown-viewer {
  color: var(--ag-text);
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}

.ag-markdown-viewer :deep(:first-child) {
  margin-top: 0;
}

.ag-markdown-viewer :deep(:last-child) {
  margin-bottom: 0;
}

.ag-markdown-viewer :deep(p),
.ag-markdown-viewer :deep(ul),
.ag-markdown-viewer :deep(ol),
.ag-markdown-viewer :deep(blockquote),
.ag-markdown-viewer :deep(pre),
.ag-markdown-viewer :deep(table) {
  margin: 0 0 10px;
}

.ag-markdown-viewer :deep(ul),
.ag-markdown-viewer :deep(ol) {
  padding-left: 18px;
}

.ag-markdown-viewer :deep(a) {
  color: var(--ag-blue);
  text-decoration: none;
}

.ag-markdown-viewer :deep(a:hover),
.ag-markdown-viewer :deep(a:focus-visible) {
  text-decoration: underline;
}

.ag-markdown-viewer :deep(code) {
  border-radius: 4px;
  background: var(--ag-code-bg);
  color: var(--ag-code-text);
  font-family: "Fira Code", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.92em;
  padding: 1px 4px;
}

.ag-markdown-viewer :deep(pre) {
  max-width: 100%;
  overflow: auto;
  border: 1px solid var(--ag-border);
  border-radius: var(--ag-radius-panel);
  background: var(--ag-code-bg);
  padding: 12px;
}

.ag-markdown-viewer :deep(pre code) {
  display: block;
  background: transparent;
  padding: 0;
}

.ag-markdown-viewer :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.ag-markdown-viewer :deep(th),
.ag-markdown-viewer :deep(td) {
  border: 1px solid var(--ag-border);
  padding: 6px 8px;
  text-align: left;
}

.ag-markdown-viewer :deep(blockquote) {
  border-left: 3px solid var(--ag-blue);
  color: var(--ag-muted-strong);
  padding-left: 10px;
}
</style>
