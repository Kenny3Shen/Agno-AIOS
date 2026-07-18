import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import commonZh from './namespaces/common.zh-CN.json'
import commonEn from './namespaces/common.en-US.json'
import authZh from './namespaces/auth.zh-CN.json'
import authEn from './namespaces/auth.en-US.json'
import shellZh from './namespaces/shell.zh-CN.json'
import shellEn from './namespaces/shell.en-US.json'
import chatZh from './namespaces/chat.zh-CN.json'
import chatEn from './namespaces/chat.en-US.json'
import dashboardZh from './namespaces/dashboard.zh-CN.json'
import dashboardEn from './namespaces/dashboard.en-US.json'
import knowledgeZh from './namespaces/knowledge.zh-CN.json'
import knowledgeEn from './namespaces/knowledge.en-US.json'
import settingsZh from './namespaces/settings.zh-CN.json'
import settingsEn from './namespaces/settings.en-US.json'
import mcpZh from './namespaces/mcp.zh-CN.json'
import mcpEn from './namespaces/mcp.en-US.json'
import approvalsZh from './namespaces/approvals.zh-CN.json'
import approvalsEn from './namespaces/approvals.en-US.json'
import auditZh from './namespaces/audit.zh-CN.json'
import auditEn from './namespaces/audit.en-US.json'
import cveZh from './namespaces/cve.zh-CN.json'
import cveEn from './namespaces/cve.en-US.json'
import collectZh from './namespaces/collect.zh-CN.json'
import collectEn from './namespaces/collect.en-US.json'
import memoryZh from './namespaces/memory.zh-CN.json'
import memoryEn from './namespaces/memory.en-US.json'
import skillsZh from './namespaces/skills.zh-CN.json'
import skillsEn from './namespaces/skills.en-US.json'
import traceZh from './namespaces/trace.zh-CN.json'
import traceEn from './namespaces/trace.en-US.json'
import evaluationsZh from './namespaces/evaluations.zh-CN.json'
import evaluationsEn from './namespaces/evaluations.en-US.json'
import workflowZh from './namespaces/workflow.zh-CN.json'
import workflowEn from './namespaces/workflow.en-US.json'

export const defaultNS = 'common' as const
export const supportedLngs = ['zh-CN', 'en-US'] as const
export type AppLocale = (typeof supportedLngs)[number]

export const resources = {
  'zh-CN': {
    common: commonZh,
    auth: authZh,
    shell: shellZh,
    chat: chatZh,
    dashboard: dashboardZh,
    knowledge: knowledgeZh,
    settings: settingsZh,
    mcp: mcpZh,
    approvals: approvalsZh,
    audit: auditZh,
    cve: cveZh,
    collect: collectZh,
    memory: memoryZh,
    skills: skillsZh,
    trace: traceZh,
    evaluations: evaluationsZh,
    workflow: workflowZh,
  },
  'en-US': {
    common: commonEn,
    auth: authEn,
    shell: shellEn,
    chat: chatEn,
    dashboard: dashboardEn,
    knowledge: knowledgeEn,
    settings: settingsEn,
    mcp: mcpEn,
    approvals: approvalsEn,
    audit: auditEn,
    cve: cveEn,
    collect: collectEn,
    memory: memoryEn,
    skills: skillsEn,
    trace: traceEn,
    evaluations: evaluationsEn,
    workflow: workflowEn,
  },
} as const

const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('locale') : null
const initialLng: AppLocale = stored === 'en-US' ? 'en-US' : 'zh-CN'

void i18n.use(initReactI18next).init({
  resources,
  lng: initialLng,
  fallbackLng: 'en-US',
  defaultNS,
  ns: Object.keys(resources['zh-CN']),
  interpolation: { escapeValue: false },
  returnNull: false,
})

if (typeof document !== 'undefined') {
  document.documentElement.lang = initialLng
}

export default i18n
