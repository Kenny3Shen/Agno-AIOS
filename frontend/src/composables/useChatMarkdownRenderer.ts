import { nextTick, ref, type Ref } from "vue"
import { ElMessage } from "element-plus"
import { copyToClipboard } from "../lib/clipboard"
import type { Message } from "../types"

export interface ParsedAssistantMessage {
  body: string
  thinking: string
  sources: string[]
  toolEvents: string[]
}

interface ChatMarkdownRendererOptions {
  t: (key: string, params?: Record<string, unknown>) => string
  isNearBottom: () => boolean
  scrollToBottom: () => Promise<void>
  blockedContentKey?: string
}

const blockedAssistantContentPattern = /^(your request was blocked\.?|request was blocked\.?)$/i

export function useChatMarkdownRenderer(options: ChatMarkdownRendererOptions) {
  const zoomedImage: Ref<string | null> = ref(null)

  const assistantDisplayContent = (message: Message) => {
    const content = message.content || ""
    if (message.role === "assistant" && blockedAssistantContentPattern.test(content.trim())) {
      return options.t(options.blockedContentKey ?? "chat.notices.requestBlocked")
    }
    return content
  }

  const parseAssistantMessage = (content: string): ParsedAssistantMessage => {
    const sources: string[] = []
    const toolEvents: string[] = []
    let thinking = ""
    let body = content

    body = body.replace(/<think>([\s\S]*?)(?:<\/think>|$)/gi, (_match, value: string) => {
      thinking = [thinking, value.trim()].filter(Boolean).join("\n\n")
      return ""
    })

    const bodyLines: string[] = []
    for (const rawLine of body.split("\n")) {
      const line = rawLine.trim()
      if (/^(思考过程|Thinking)\s*[:：]/i.test(line)) {
        thinking = [thinking, line.replace(/^(思考过程|Thinking)\s*[:：]\s*/i, "").trim() || options.t("chat.notices.thinkingFallback")]
          .filter(Boolean)
          .join("\n\n")
        continue
      }
      if (/^(来源|Source|Sources|References|引用)\s*[:：]/i.test(line)) {
        sources.push(line)
        continue
      }
      if (/^(tool|工具调用|MCP|function call)\b/i.test(line) || /\b(tool|MCP|function call)\b/i.test(line)) {
        toolEvents.push(line)
        continue
      }
      bodyLines.push(rawLine)
    }

    return {
      body: bodyLines.join("\n").trim(),
      thinking,
      sources,
      toolEvents: toolEvents.slice(0, 8),
    }
  }

  const enhanceRenderedMarkdown = async () => {
    await nextTick()
    const stickToBottom = options.isNearBottom()

    document.querySelectorAll<HTMLElement>(".agent-chat pre").forEach((pre) => {
      if (pre.querySelector(".code-copy")) return
      const code = pre.querySelector("code")
      if (!code) return

      const button = document.createElement("button")
      button.type = "button"
      button.className = "code-copy"
      button.textContent = options.t("chat.code.copy")
      button.addEventListener("click", async () => {
        if (await copyToClipboard(code.textContent || "")) {
          ElMessage.success(options.t("common.clipboard.copied"))
        } else {
          ElMessage.warning(options.t("common.clipboard.failed"))
        }
      })
      pre.appendChild(button)
    })

    document.querySelectorAll<HTMLImageElement>(".agent-chat .ag-markdown-viewer img, .agent-chat .markdown-body img").forEach((image) => {
      if (image.dataset.zoomBound === "true") return
      image.dataset.zoomBound = "true"
      image.addEventListener("click", () => {
        zoomedImage.value = image.currentSrc || image.src
      })
      image.addEventListener("load", () => {
        if (stickToBottom) void options.scrollToBottom()
      }, { once: true })
    })

    if (stickToBottom) void options.scrollToBottom()
  }

  return {
    zoomedImage,
    assistantDisplayContent,
    parseAssistantMessage,
    enhanceRenderedMarkdown,
  }
}
