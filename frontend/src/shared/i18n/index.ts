import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

const resources = {
  'zh-CN': { translation: {
    common: { refresh: '刷新', save: '保存', cancel: '取消', delete: '删除', search: '搜索', loading: '加载中', empty: '暂无数据', actions: '操作', status: '状态', details: '详情', create: '新建', copy: '复制' },
    auth: { title: '登录 T.A.I.S', subtitle: 'Trinity AI Security 工作台', email: '邮箱', password: '密码', signIn: '登录', failed: '登录失败' },
    shell: { home: '工作台', dashboard: '运行概览', chat: '安全对话', workflow: '工作流', skills: 'Skills', mcp: 'MCP', knowledge: '知识库', trace: '观测', memory: '记忆', evaluations: '评估', approvals: '审批', cve: 'CVE', collect: 'Collect', audit: '审计', settings: '设置', logout: '退出登录', theme: '切换主题', language: '切换语言' },
  } },
  'en-US': { translation: {
    common: { refresh: 'Refresh', save: 'Save', cancel: 'Cancel', delete: 'Delete', search: 'Search', loading: 'Loading', empty: 'No data', actions: 'Actions', status: 'Status', details: 'Details', create: 'Create', copy: 'Copy' },
    auth: { title: 'Sign in to T.A.I.S', subtitle: 'Trinity AI Security workspace', email: 'Email', password: 'Password', signIn: 'Sign in', failed: 'Sign in failed' },
    shell: { home: 'Workspace', dashboard: 'Overview', chat: 'Security chat', workflow: 'Workflow', skills: 'Skills', mcp: 'MCP', knowledge: 'Knowledge', trace: 'Trace', memory: 'Memory', evaluations: 'Evaluations', approvals: 'Approvals', cve: 'CVE', collect: 'Collect', audit: 'Audit', settings: 'Settings', logout: 'Sign out', theme: 'Toggle theme', language: 'Change language' },
  } },
} as const

void i18n.use(initReactI18next).init({ resources, lng: 'zh-CN', fallbackLng: 'en-US', interpolation: { escapeValue: false } })

export default i18n
