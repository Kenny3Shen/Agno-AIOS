import MarkdownIt from "markdown-it"
import { tracePayloadTextForMode, type TracePayloadViewMode } from "../modules/traceWorkbench"
import type { ParsedSpanPayload } from "../types"

export const useTracePayloadRenderer = () => {
  const markdownRenderer = new MarkdownIt({
    html: false,
    linkify: true,
    breaks: true,
  })

  const payloadTextForMode = tracePayloadTextForMode

  const renderMarkdown = (value: string) => {
    return markdownRenderer.render(value || "")
  }

  const renderPayloadMarkupForMode = (
    payload: ParsedSpanPayload,
    mode: TracePayloadViewMode,
    fallback: string,
  ) => {
    const text = payloadTextForMode(payload, mode, fallback)
    if (mode === "markdown") return renderMarkdown(text)
    return renderMarkdown(markdownRenderer.utils.escapeHtml(text))
  }

  return {
    payloadTextForMode,
    renderPayloadMarkupForMode,
  }
}
