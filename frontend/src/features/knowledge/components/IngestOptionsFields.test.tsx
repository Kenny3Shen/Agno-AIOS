import { Form, Input } from 'antd'
import { screen } from '@testing-library/react'
import { setupUser } from '@/test/user'
import { describe, expect, it } from 'vitest'
import { renderWithQuery } from '@/test/render'
import { IngestOptionsFields } from './IngestOptionsFields'

function renderOptions(initialValues: Record<string, unknown>) {
  return renderWithQuery(
    <Form layout="vertical" initialValues={initialValues}>
      <Form.Item name="file_name" label="File name">
        <Input />
      </Form.Item>
      <IngestOptionsFields />
    </Form>
  )
}

describe('knowledge ingest option fields', () => {
  it('shows Markdown options and explains chunk size tradeoffs', async () => {
    const user = setupUser()
    renderOptions({ file_name: 'runbook.md' })

    expect(screen.getByText('Markdown')).toBeTruthy()
    await user.click(screen.getByText('高级分块参数'))

    expect(screen.getByText('Markdown 标题切分')).toBeTruthy()
    expect(screen.getByText('章节上限')).toBeTruthy()
    await user.hover(screen.getByLabelText('章节上限 help'))
    expect(await screen.findByText('单个 chunk 的目标/最大长度；越小检索越精确，越大上下文越完整。')).toBeTruthy()
  })

  it('switches options when replacement filename changes', async () => {
    const user = setupUser()
    renderOptions({ file_name: 'runbook.csv' })

    await user.click(screen.getByText('高级分块参数'))
    expect(screen.getByText('CSV 跳过表头')).toBeTruthy()

    await user.clear(screen.getByLabelText('File name'))
    await user.type(screen.getByLabelText('File name'), 'agent.ts')

    expect(await screen.findByText('代码分块大小')).toBeTruthy()
    expect(screen.getByText('代码分词器')).toBeTruthy()
  })

  it('uses semantic options for plain text and no suffix input', async () => {
    const user = setupUser()
    renderOptions({ file_name: 'notes.txt' })

    await user.click(screen.getByText('高级分块参数'))

    expect(screen.getByText('语义阈值')).toBeTruthy()
    expect(screen.getByText('语义窗口')).toBeTruthy()
    expect(screen.getByText('最少句子数')).toBeTruthy()
  })
})
