import assert from "node:assert/strict"
import { memoryControl, panelHeader, visibilityTabs } from "./modules/testSource.mjs"

import "./modules/shellNavigation.test.mjs"
import "./modules/knowledgeWorkbench.test.mjs"
import "./modules/agentEvalsWorkbench.test.mjs"
import "./modules/memoryControl.test.mjs"
import "./modules/traceWorkbench.test.mjs"
import "./modules/workflowBuilder.test.mjs"
import "./modules/schedulerAgentOsApi.test.mjs"
import "./modules/resourceVisibility.test.mjs"
import "./modules/shellCoreSourceContracts.test.mjs"
import "./modules/navigationSettingsSourceContracts.test.mjs"
import "./modules/surfaceLayoutSourceContracts.test.mjs"
import "./modules/agentEvalTraceSourceContracts.test.mjs"
import "./modules/knowledgeSettingsSourceContracts.test.mjs"
import "./modules/apiComposablesSourceContracts.test.mjs"
import "./modules/utilityFirstPrimitivesSourceContracts.test.mjs"
import "./modules/knowledgeUpdateSourceContracts.test.mjs"

assert.match(
  memoryControl,
  /grid-template-columns: minmax\(260px, 280px\) minmax\(0, 1fr\) minmax\(320px, 360px\)/,
  "Memory queue column must leave enough room for its heading and threshold summary",
)

assert.match(
  memoryControl,
  /@media \(max-width: 1120px\)[\s\S]*?\.mem-workbench > :nth-child\(3\)[\s\S]*?grid-column: 1 \/ -1/,
  "Memory detail panel must span both columns at the intermediate breakpoint",
)

assert.match(panelHeader, /class="flex flex-none items-center gap-2"/, "Panel header actions must retain their intrinsic width")
assert.doesNotMatch(panelHeader, /\bflex-0\b/, "Panel header actions must not collapse to zero width")
assert.match(visibilityTabs, /:value="option\.value"/, "Element Plus radio buttons must use the current value API")
assert.doesNotMatch(visibilityTabs, /:label="option\.value"/, "Visibility tabs must not use deprecated label-as-value behavior")
