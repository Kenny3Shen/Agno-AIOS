import { computed, ref } from "vue"
import { defineStore } from "pinia"

export type LocaleCode = "zh-CN" | "en-US"

export const useShellStore = defineStore("shell", () => {
  const activeTab = ref("home")
  const isSidebarCompact = ref(false)
  const isMobile = ref(false)
  const sidebarOpen = ref(false)
  const isDark = ref(true)
  const componentRenderKey = ref(0)
  const chatSessionsExpanded = ref(true)
  const traceQueueExpanded = ref(true)
  const locale = ref<LocaleCode>("zh-CN")

  const shellThemeClass = computed(() => (isDark.value ? "dark" : "light"))

  const setActiveTab = (tab: string) => {
    activeTab.value = tab
  }

  const setIsMobile = (value: boolean) => {
    isMobile.value = value
  }

  const setSidebarOpen = (value: boolean) => {
    sidebarOpen.value = value
  }

  const setSidebarCompact = (value: boolean) => {
    isSidebarCompact.value = value
  }

  const setDark = (value: boolean) => {
    isDark.value = value
  }

  const bumpRenderKey = () => {
    componentRenderKey.value += 1
  }

  const setChatSessionsExpanded = (value: boolean) => {
    chatSessionsExpanded.value = value
  }

  const setTraceQueueExpanded = (value: boolean) => {
    traceQueueExpanded.value = value
  }

  const setLocale = (value: LocaleCode) => {
    locale.value = value
    document.documentElement.lang = value
  }

  return {
    activeTab,
    isSidebarCompact,
    isMobile,
    sidebarOpen,
    isDark,
    componentRenderKey,
    chatSessionsExpanded,
    traceQueueExpanded,
    locale,
    shellThemeClass,
    setActiveTab,
    setIsMobile,
    setSidebarOpen,
    setSidebarCompact,
    setDark,
    bumpRenderKey,
    setChatSessionsExpanded,
    setTraceQueueExpanded,
    setLocale,
  }
})
