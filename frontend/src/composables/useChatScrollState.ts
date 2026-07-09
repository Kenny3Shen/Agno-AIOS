import { nextTick, ref, type Ref } from "vue"

export function useChatScrollState(chatContainer: Readonly<Ref<HTMLElement | null>>) {
  const pendingNewMessages = ref(0)
  const showScrollToBottom = ref(false)
  const showBackToTop = ref(false)

  const isNearBottom = () => {
    const container = chatContainer.value
    if (!container) return true
    return container.scrollHeight - container.clientHeight - container.scrollTop < 120
  }

  const updateScrollState = () => {
    const container = chatContainer.value
    if (!container) {
      showScrollToBottom.value = false
      showBackToTop.value = false
      return
    }

    const nearBottom = isNearBottom()
    showScrollToBottom.value = !nearBottom
    showBackToTop.value = container.scrollTop > 360
    if (nearBottom) pendingNewMessages.value = 0
  }

  const scrollToBottom = async () => {
    await nextTick()
    const container = chatContainer.value
    if (container) {
      container.scrollTop = container.scrollHeight
    }
    pendingNewMessages.value = 0
    updateScrollState()
  }

  const scrollToBottomAndClear = () => {
    void scrollToBottom()
  }

  const scrollToTop = async () => {
    await nextTick()
    chatContainer.value?.scrollTo({ top: 0, behavior: "smooth" })
    updateScrollState()
  }

  const handleChatScroll = () => {
    updateScrollState()
  }

  const followStreamPosition = (shouldStick: boolean) => {
    if (shouldStick) {
      void scrollToBottom()
      return
    }

    pendingNewMessages.value = Math.max(1, pendingNewMessages.value)
    updateScrollState()
  }

  return {
    pendingNewMessages,
    showScrollToBottom,
    showBackToTop,
    isNearBottom,
    updateScrollState,
    scrollToBottom,
    scrollToBottomAndClear,
    scrollToTop,
    handleChatScroll,
    followStreamPosition,
  }
}
