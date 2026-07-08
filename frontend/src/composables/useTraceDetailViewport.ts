export const useTraceDetailViewport = () => {
  const scrollDetailIntoView = () => {
    if (!window.matchMedia("(max-width: 980px)").matches) return
    requestAnimationFrame(() => {
      document.querySelector<HTMLElement>(".trace-detail-panel")?.scrollIntoView({ block: "start", behavior: "smooth" })
    })
  }

  return {
    scrollDetailIntoView,
  }
}
