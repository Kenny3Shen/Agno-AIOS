import { nextTick, ref, type Ref } from "vue"
import {
  traceDetailTabForSection,
  type TraceDetailSection,
  type TraceDetailTab,
} from "../modules/traceWorkbench"
import type { SpanItem, SpanTreeNode } from "../types"

interface UseTraceSpanSelectionParams {
  selectedSpan: Ref<SpanItem | null>
}

export const useTraceSpanSelection = ({ selectedSpan }: UseTraceSpanSelectionParams) => {
  const activeDetailTab = ref<TraceDetailTab>("info")

  const scrollDetailSectionIntoView = async (section: TraceDetailSection) => {
    await nextTick()
    const target = document.getElementById(`trace-detail-${section}`)
    target?.scrollIntoView({ block: "start", behavior: "smooth" })
  }

  const selectSpan = (span: SpanItem, section: TraceDetailSection = "input") => {
    selectedSpan.value = span
    activeDetailTab.value = traceDetailTabForSection(section)
    void scrollDetailSectionIntoView(section)
  }

  const onSpanNodeClick = (node: SpanTreeNode) => {
    selectSpan(node.span)
  }

  return {
    activeDetailTab,
    selectSpan,
    onSpanNodeClick,
  }
}
