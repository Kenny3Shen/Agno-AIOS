import { Link } from '@tanstack/react-router'
import { ArrowRightOutlined, RadarChartOutlined } from '@ant-design/icons'
import { Button, Tag, Typography } from 'antd'

const workspaces = [
  { to: '/chat', code: 'OPS-01', title: '安全对话', description: '运行具备工具与知识上下文的安全分析。', signal: 'STREAM' },
  { to: '/trace', code: 'OBS-02', title: 'Trace 观测', description: '定位会话、运行和 Span 级异常。', signal: 'LIVE' },
  { to: '/knowledge', code: 'DATA-03', title: '知识库', description: '管理检索资产、可见性与入库流水线。', signal: 'INDEXED' },
  { to: '/approvals', code: 'GOV-04', title: '运行治理', description: '处理暂停任务、审批和调度策略。', signal: 'POLICY' },
] as const

export function HomePage() {
  return (
    <main className="home-page">
      <section className="home-command">
        <div><Tag variant="filled">TRINITY AI SECURITY</Tag><Typography.Title>T.A.I.S 工作台</Typography.Title><Typography.Paragraph>面向安全运营人员的 Agent 运行、知识、观测与治理工作台。</Typography.Paragraph></div>
        <div className="home-radar"><RadarChartOutlined /><span>14</span><small>ACTIVE MODULES</small></div>
      </section>
      <section className="signal-rail"><span><i className="green" />DATA PLANE READY</span><span><i className="blue" />RUNTIME CONNECTED</span><span><i className="orange" />POLICY ENFORCED</span></section>
      <section className="workspace-grid">
        {workspaces.map((item) => <article key={item.code} className="workspace-row"><span className="workspace-code">{item.code}</span><div><h2>{item.title}</h2><p>{item.description}</p></div><Tag>{item.signal}</Tag><Link to={item.to}><Button type="text" icon={<ArrowRightOutlined />} aria-label={item.title} /></Link></article>)}
      </section>
    </main>
  )
}
