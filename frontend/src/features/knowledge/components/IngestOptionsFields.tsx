import { Collapse, Form, InputNumber, Select } from 'antd'

const readerStrategies = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'semantic', label: 'Semantic text' },
  { value: 'code', label: 'Code' },
  { value: 'csv_row', label: 'CSV rows' },
  { value: 'json', label: 'JSON' },
]

export function IngestOptionsFields() {
  return (
    <Collapse
      className="knowledge-advanced-options"
      ghost
      items={[{
        key: 'advanced',
        label: '高级分块参数',
        children: (
          <div className="knowledge-advanced-grid">
            <Form.Item name={['ingest_options', 'chunk_size']} label="Chunk size" tooltip="普通文本分块大小，留空使用全局配置">
              <InputNumber min={200} precision={0} placeholder="默认" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name={['ingest_options', 'chunk_overlap']} label="Overlap" tooltip="相邻 chunk 重叠长度，必须小于 Chunk size">
              <InputNumber min={0} precision={0} placeholder="默认" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name={['ingest_options', 'code_chunk_size']} label="Code chunk size" tooltip="代码文件分块大小">
              <InputNumber min={256} precision={0} placeholder="默认" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name={['ingest_options', 'semantic_threshold']} label="Semantic threshold" tooltip="语义分块阈值，0 到 1">
              <InputNumber min={0} max={1} step={0.01} placeholder="默认" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name={['ingest_options', 'reader_strategy']} label="Reader strategy" tooltip="显式覆盖后缀推断的 Reader">
              <Select allowClear placeholder="自动选择" options={readerStrategies} />
            </Form.Item>
          </div>
        ),
      }]}
    />
  )
}
