import assert from "node:assert/strict"
import {
  agentEvals,
  removedAgentOsControlSource,
  apiClient,
  app,
  appStyle,
  assertNoPillStatChip,
  assertTextOrder,
  authScreen,
  authStoreSource,
  chat,
  clipboard,
  collect,
  cve,
  dashboard,
  designTokens,
  existsSync,
  hasRoleScope,
  hasUserScope,
  i18n,
  knowledge,
  knowledgeDocumentList,
  knowledgeIngestDrawer,
  mcp,
  memoryControl,
  readOptionalSource,
  readSource,
  scopes,
  settings,
  shellBrand,
  shellNavigation,
  skills,
  sourcePath,
  trace,
  typesSource,
  userRole,
  visibilityTabs,
  workflow,
} from "./testSource.mjs"

assert.equal(
  app.includes("ag-nav-desc"),
  false,
  "sidebar navigation must not render secondary explanatory text",
)

for (const locale of ["zh-CN", "en-US"]) {
  i18n.global.locale.value = locale
  assert.doesNotThrow(
    () => i18n.global.t("mcp.upload.manifestPlaceholder"),
    `MCP upload manifest placeholder must compile in ${locale}`,
  )
}

assert.equal(
  app.includes("ag-user-chip"),
  false,
  "topbar must not render the user identity; the sidebar footer is the single user location",
)

assert.equal(
  app.includes("<p>{{ currentMeta.description }}</p>"),
  false,
  "topbar must stay compact and avoid rendering duplicate page descriptions",
)

assert.equal(
  app.includes("ag-command"),
  false,
  "home must avoid the previous oversized hero block",
)

assert.equal(
  app.includes("ag-plane-grid"),
  false,
  "home must avoid the extra runtime overview card wall",
)

assert.equal(
  app.includes("ag-topbar-button"),
  false,
  "topbar refresh control must use the compact icon treatment",
)

assert.match(
  app,
  /ag-topbar-icon/,
  "topbar actions must use compact icon buttons",
)

const topbarActionsTemplate = app.match(/<div class="ag-topbar-actions">[\s\S]*?<\/div>\s*<\/header>/)?.[0] ?? ""

assert.doesNotMatch(
  topbarActionsTemplate,
  /<el-tooltip/,
  "topbar refresh, theme, and GitHub icon buttons must not open hover tooltip popovers",
)

assert.match(
  appStyle,
  /html\.dark\s*:where\(\.el-tooltip\.el-popper:not\(\.el-select__popper\),\s*\.el-tooltip__popper\)[\s\S]*background:\s*var\(--ag-panel-raised\)\s*!important[\s\S]*color:\s*var\(--ag-text\)\s*!important/,
  "dark mode tooltips must inherit the dark shell surface instead of Element Plus light tooltip styling",
)

assert.match(
  appStyle,
  /html:not\(\.dark\)\s*:where\(\.el-tooltip\.el-popper:not\(\.el-select__popper\),\s*\.el-tooltip__popper\)[\s\S]*background:\s*var\(--ag-panel-raised\)\s*!important[\s\S]*color:\s*var\(--ag-heading\)\s*!important/,
  "light mode tooltips must inherit the light shell surface instead of forcing the dark-mode tooltip treatment",
)

assert.match(
  appStyle,
  /:where\(\.el-tooltip\.el-popper:not\(\.el-select__popper\),\s*\.el-tooltip__popper\)\s*:where\(\.el-popper__arrow\)\s*\{[\s\S]*display:\s*none\s*!important;/,
  "tooltips must hide the Element Plus arrow diamond",
)

assert.match(
  shellBrand,
  /PRODUCT_SHORT_NAME = "T\.A\.I\.S"/,
  "shell brand constants must expose the T.A.I.S short name",
)

assert.match(
  shellBrand,
  /PRODUCT_FULL_NAME = "Trinity AI Security"/,
  "shell brand constants must expose the Trinity AI Security full name",
)

assert.match(
  shellBrand,
  /GITHUB_REPOSITORY_URL = "https:\/\/github\.com\/Kenny3Shen\/Agno-AIOS"/,
  "shell brand constants must expose the repository URL used by the GitHub button",
)

assert.match(
  app,
  /openRepository/,
  "topbar must wire a GitHub repository action",
)

assertTextOrder(
  app,
  [
    ':aria-label="isDark ? t(\'shell.theme.toLight\') : t(\'shell.theme.toDark\')"',
    ':aria-label="t(\'shell.actions.github\')"',
  ],
  "GitHub button must sit to the right of the theme toggle",
)

assert.equal(
  app.includes(">GH<"),
  false,
  "GitHub repository action must use an icon instead of a text abbreviation",
)

assert.match(
  app,
  /ag-github-icon/,
  "GitHub repository action must render a GitHub icon",
)

assert.match(
  app,
  /ag-sidebar-toggle/,
  "sidebar must use a visible toggle button instead of pointer drag resizing",
)

assert.match(
  app,
  /gridTemplateColumns:\s*isMobile\.value\s*\?\s*undefined\s*:/,
  "mobile shell must not keep desktop sidebar grid columns while using a fixed overlay sidebar",
)

assert.equal(
  app.includes("ag-pro-chip"),
  false,
  "sidebar brand must not render the current model chip because it overflows on narrow sidebars",
)

assert.equal(
  app.includes("currentModelLabel"),
  false,
  "App shell must not keep sidebar-only current model label state after removing the chip",
)

assert.match(
  app,
  /useI18n\(\)/,
  "App shell must read display copy from vue-i18n",
)

assert.match(
  app,
  /setI18nLocale/,
  "App shell must synchronize the shell locale store with vue-i18n",
)

assert.match(
  app,
  /t\("shell\.nav\.home\.label"\)/,
  "App shell navigation labels must be sourced from i18n messages",
)

for (const hardcodedShellCopy of [
  ">New chat<",
  ">Sessions<",
  ">No sessions<",
  ">Refresh traces<",
  ">Trace Observability<",
  "关闭导航遮罩",
  "当前会话",
  "已认证",
  "运行平面",
  "未登录",
  "运营控制面",
  "资产、漏洞、知识入库",
  "对话、MCP、Trace 观测",
  "会话加载失败",
  "Trace 队列加载失败",
  "会话已归档",
  "归档会话失败",
  ">打开<",
  ">No traces<",
]) {
  assert.equal(
    app.includes(hardcodedShellCopy),
    false,
    `App shell must not hardcode sidebar copy: ${hardcodedShellCopy}`,
  )
}

assert.equal(
  app.includes("startSidebarResize"),
  false,
  "sidebar resizing must not use drag handlers",
)

assert.equal(
  authScreen.includes("auth-copy"),
  false,
  "unauthenticated screen must avoid the previous long marketing copy panel",
)

assert.match(
  authScreen,
  /auth-brief/,
  "unauthenticated screen must use the compact shared shell visual language",
)

assert.doesNotMatch(
  authScreen,
  />Agno<|>AIOS</,
  "AuthScreen must use shared T.A.I.S brand constants instead of hardcoded old brand copy",
)

assert.match(
  authScreen,
  /auth\.brief\.items\.chat/,
  "AuthScreen brief chips must be sourced from i18n",
)

assert.match(
  authScreen,
  /auth\.oauth\.label/,
  "AuthScreen OAuth label must be sourced from i18n",
)

assert.match(
  authScreen,
  /auth\.footer\.jwt/,
  "AuthScreen footer technology chips must be sourced from i18n",
)

assert.match(
  authScreen,
  /useI18n\(\)/,
  "AuthScreen must read user-facing copy from vue-i18n",
)

assert.match(
  authStoreSource,
  /hasUserScope/,
  "auth store must use server-issued scope claims through the shared helper",
)

assert.equal(
  userRole({ role: "guest", is_superuser: true }),
  "admin",
  "shared auth helpers must elevate FastAPI Users superusers to admin in shell state",
)

assert.match(
  authStoreSource,
  /hasScope = \(scope: string\)/,
  "auth store must expose a reusable scope helper",
)

assert.match(
  scopes,
  /ROLE_SCOPES/,
  "frontend RBAC helper must keep a role scope fallback for unauthenticated shell state",
)

assert.equal(
  hasUserScope({ role: "guest", scopes: ["memories:write"] }, "memories:write"),
  true,
  "scope claims from the backend must take precedence over the role fallback",
)

assert.equal(
  hasUserScope({ role: "user", scopes: ["sessions:read"] }, "memories:write"),
  false,
  "missing scope claims must not be re-expanded from the user's role",
)

assert.equal(
  hasUserScope({ role: "guest", permissions: ["agent_os:admin"] }, "config:write"),
  false,
  "removed permissions claims must not grant frontend access",
)

assert.match(
  scopes,
  /"collect:write"/,
  "frontend RBAC helper must reflect write-only modules such as Collect",
)

assert.match(
  scopes,
  /evals:read/,
  "frontend scopes must include AgentOS eval read scope",
)

assert.match(
  scopes,
  /evals:write/,
  "frontend scopes must include AgentOS eval write scope",
)

assert.match(
  scopes,
  /evals:delete/,
  "frontend scopes must include AgentOS eval delete scope for admin fallback",
)

assert.equal(
  hasRoleScope("user", "memories:write"),
  true,
  "ordinary users must be able to update and delete their own memories",
)

assert.equal(
  hasRoleScope("guest", "memories:write"),
  false,
  "guest users must not be able to mutate memories",
)

for (const hardcodedAuthCopy of [
  "登录后继续使用 Chat、MCP、Trace 与模型设置。",
  "进入工作台",
  "创建账号",
  "登录",
  "注册",
  "邮箱",
  "密码",
  "至少 8 位",
  "进入 T.A.I.S",
  "创建并进入",
  "请输入有效邮箱",
  "密码至少需要 8 位",
  "认证失败",
  "OAuth 授权失败",
]) {
  assert.equal(
    authScreen.includes(hardcodedAuthCopy),
    false,
    `AuthScreen must not hardcode auth copy: ${hardcodedAuthCopy}`,
  )
}

assert.equal(
  app.includes("ag-nav-section-title"),
  false,
  "expanded sidebar must not render category titles",
)

for (const category of ["安全运营", "数据底座", "AI 编排", "系统治理"]) {
  assert.equal(
    app.includes(category),
    false,
    `sidebar grouping must not expose the old category label: ${category}`,
  )
}

assert.match(
  app,
  /ag-nav-divider/,
  "sidebar nav must use simple divider grouping",
)

assert.match(
  app,
  /dashboardItem/,
  "Dashboard must be modeled separately so it can sit directly under Home",
)

assert.match(
  app,
  /ag-home-summary/,
  "Home must use the compact summary strip",
)

assert.match(
  app,
  /ag-module-tile/,
  "Home modules must render as compact direct-action tiles",
)

assert.match(
  app,
  /buildShellHomeSections\([\s\S]*sidebarNavGroups\.value/,
  "Home module groups must derive from the sidebar navigation groups",
)

assert.doesNotMatch(
  app,
  /buildShellHomeSections\([\s\S]*navItemById\.value/,
  "Home module groups must not keep a separate grouping map from the sidebar",
)

assert.equal(
  mcp.includes("xl:grid-cols-[minmax(0,1fr)_320px]"),
  false,
  "MCP must avoid the previous wide right-side context rail",
)

assert.match(
  mcp,
  /mcp-toolbar ag-content-panel/,
  "MCP must use a business toolbar for service context and upload actions",
)

assert.match(
  mcp,
  /DataChip/,
  "MCP toolbar must keep service metrics in shared DataChip primitives",
)

assert.doesNotMatch(
  mcp,
  /t\('mcp\.actions\.refresh'\)|t\("mcp\.actions\.refresh"\)/,
  "MCP must rely on the shell title-bar refresh button instead of rendering a page refresh button",
)

assert.doesNotMatch(
  mcp,
  /mcp-summary-strip/,
  "MCP must not keep the old page-level summary strip",
)

assert.doesNotMatch(
  mcp,
  /mcp-toolbar ag-content-panel[\s\S]{0,800}mcp-summary-strip|\.mcp-summary-url\s*\{[^}]*flex:/s,
  "MCP toolbar must not wrap or resize the Knowledge-style summary strip",
)

assert.doesNotMatch(
  skills,
  /t\('skills\.actions\.refresh'\)|t\("skills\.actions\.refresh"\)/,
  "Skills must rely on the shell title-bar refresh button instead of rendering a page refresh button",
)

assert.doesNotMatch(
  skills,
  /skills-action-bar/,
  "Skills upload action must be integrated into the summary strip, not isolated in a standalone toolbar container",
)

assert.match(
  skills,
  /skill-workbench/,
  "Skills must render a split workbench instead of the previous card grid",
)

assert.match(
  skills,
  /skill-list-panel/,
  "Skills workbench must keep the Skill list on the left",
)

assert.match(
  skills,
  /skill-detail-panel/,
  "Skills workbench must show selected Skill metadata on the right",
)

assert.match(
  skills,
  /selectedSkill/,
  "Skills workbench must track the selected Skill for the metadata panel",
)

assert.match(
  skills,
  /skill-metadata-grid/,
  "Skills detail panel must expose SKILL.md-style metadata fields",
)

assert.match(
  skills,
  /skillWorkbenchStyle/,
  "Skills workbench must default to a 20/80 split through a controlled style variable",
)

assert.match(
  skills,
  /skill-resize-handle/,
  "Skills workbench must expose a manual resize handle between the list and detail panes",
)

assert.match(
  skills,
  /startSkillResize/,
  "Skills resize handle must wire pointer-based manual resizing",
)

assert.match(
  skills,
  /skill-detail-tabs/,
  "Skills detail panel must separate Metadata and detail into tabs",
)

assert.match(
  skills,
  /skill-detail-source/,
  "Skills detail tab must render the raw SKILL.md source",
)

assert.match(
  skills,
  /import MarkdownIt from "markdown-it"/,
  "Skills detail tab must use MarkdownIt for rendered SKILL.md content",
)

assert.match(
  skills,
  /v-html="renderSelectedSkillMarkdown\(\)"/,
  "Skills detail tab must render Markdown HTML instead of a raw pre block",
)

assert.match(
  skills,
  /formatSkillMarkdownForRender/,
  "Skills detail tab must normalize SKILL.md frontmatter before Markdown rendering",
)

assert.match(
  skills,
  /\["```yaml", frontmatter, "```", body\]/,
  "Skills detail tab must render SKILL.md frontmatter as a YAML code fence",
)

assert.doesNotMatch(
  skills,
  /<pre class="skill-detail-source"/,
  "Skills detail tab must not display SKILL.md as unrendered plain text",
)

assert.match(
  skills,
  /<StatusChip[\s\S]*skill\.enabled \? 'green' : 'muted'/,
  "Skills list enabled/disabled state must use the shared status chip with bounded tones",
)

assert.match(
  skills,
  /skill_markdown/,
  "Skills UI must consume the API-provided SKILL.md source",
)

assert.match(
  typesSource,
  /skill_markdown:\s*string/,
  "SkillInfo type must include the raw SKILL.md source field",
)

assert.doesNotMatch(
  skills,
  /skills-grid/,
  "Skills must not keep the old card grid layout",
)

assert.match(
  visibilityTabs,
  /resource-visibility-tabs/,
  "Private/Public controls must use the shared visibility tabs component",
)

for (const visibilityConsumer of [
  ["Skills", skills],
  ["MCP", mcp],
  ["Knowledge", [knowledge, knowledgeDocumentList, knowledgeIngestDrawer].join("\n")],
]) {
  assert.match(
    visibilityConsumer[1],
    /ResourceVisibilityTabs/,
    `${visibilityConsumer[0]} must use the shared Private/Public tabs`,
  )
}

for (const locale of ["zh-CN", "en-US"]) {
  i18n.global.locale.value = locale
  assert.equal(
    i18n.global.t("skills.tabs.detail"),
    "Detail",
    `Skills detail tab label must use title case in ${locale}`,
  )
}
