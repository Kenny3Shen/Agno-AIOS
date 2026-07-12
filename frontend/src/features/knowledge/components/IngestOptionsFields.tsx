import { Collapse, Form, InputNumber, Select, Space, Switch, Tag, Tooltip, Typography, type UploadFile } from 'antd'
import { QuestionCircleOutlined } from '@ant-design/icons'
import type { KnowledgeIngestDefaults } from '../utils'
import { inferKnowledgeReaderProfile, selectedUploadFile } from '../utils'

const readerStrategies = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'semantic', label: 'Semantic text' },
  { value: 'code', label: 'Code' },
  { value: 'csv_row', label: 'CSV rows' },
  { value: 'json', label: 'JSON' },
  { value: 'document', label: 'Document' },
]

const headingSplitOptions = [
  { value: 0, label: '按大小切分' },
  { value: 1, label: 'H1' },
  { value: 2, label: 'H1-H2' },
  { value: 3, label: 'H1-H3' },
  { value: 4, label: 'H1-H4' },
  { value: 5, label: 'H1-H5' },
  { value: 6, label: 'H1-H6' },
]

const tokenizerOptions = [
  { value: 'character', label: 'character' },
  { value: 'gpt2', label: 'gpt2' },
]

const tooltips = {
  reader_strategy: '覆盖后缀自动推断；通常保持自动即可。',
  chunk_size: '单个 chunk 的目标/最大长度；越小检索越精确，越大上下文越完整。',
  chunk_overlap: '相邻 chunk 共享的字符数；提升上下文连续性，但会增加索引量。',
  markdown_split_on_headings: '按标题层级切分；例如 H1-H2 会保留 H3 及以下内容在所属 H2 内。',
  code_chunk_size: '代码 chunk 的最大长度；过小可能拆散函数，过大检索粒度变粗。',
  code_tokenizer: '用于估算代码长度；默认 character 更稳定，gpt2 更接近 token 粒度。',
  code_include_nodes: '是否在代码 chunk 中保留 AST 节点信息；用于调试或更细粒度结构信息。',
  csv_skip_header: '是否跳过首行表头；首行是字段名时建议开启。',
  csv_clean_rows: '是否清理行内容空白；通常保持开启。',
  semantic_threshold: '语义相似度阈值；越低越容易切分，越高越倾向合并。',
  semantic_similarity_window: '比较语义变化时参考的句子窗口大小；越大越平滑。',
  semantic_min_sentences_per_chunk: '每个语义 chunk 至少包含的句子数。',
  semantic_min_characters_per_sentence: '过短句子低于该长度时不作为稳定切分依据。',
} as const

function HelpLabel({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <Space size={4}>
      <span>{label}</span>
      <Tooltip title={tooltip}>
        <QuestionCircleOutlined aria-label={`${label} help`} className="knowledge-option-help" />
      </Tooltip>
    </Space>
  )
}

function NumberField({
  name,
  label,
  tooltip,
  placeholder,
  min,
  max,
  step,
}: {
  name: string
  label: string
  tooltip: string
  placeholder?: string
  min?: number
  max?: number
  step?: number
}) {
  return (
    <Form.Item preserve={false} name={['ingest_options', name]} label={<HelpLabel label={label} tooltip={tooltip} />}>
      <InputNumber
        min={min}
        max={max}
        step={step}
        precision={step && step < 1 ? 2 : 0}
        placeholder={placeholder ?? '默认'}
        style={{ width: '100%' }}
      />
    </Form.Item>
  )
}

function SwitchField({ name, label, tooltip, defaultChecked }: { name: string; label: string; tooltip: string; defaultChecked?: boolean }) {
  return (
    <Form.Item
      preserve={false}
      initialValue={defaultChecked}
      name={['ingest_options', name]}
      label={<HelpLabel label={label} tooltip={tooltip} />}
      valuePropName="checked"
    >
      <Switch />
    </Form.Item>
  )
}

export function IngestOptionsFields({ defaults }: { defaults?: KnowledgeIngestDefaults }) {
  const fileList = Form.useWatch('fileList') as UploadFile[] | undefined
  const fileName = Form.useWatch('file_name') as string | undefined
  const title = Form.useWatch('title') as string | undefined
  const readerStrategy = Form.useWatch(['ingest_options', 'reader_strategy']) as string | undefined
  const markdownHeadingMode = Form.useWatch(['ingest_options', 'markdown_split_on_headings']) as number | undefined
  const selectedFileName = selectedUploadFile(fileList)?.name
  const effectiveName = selectedFileName || fileName || title || ''
  const profile = inferKnowledgeReaderProfile(effectiveName, readerStrategy)
  const chunkLabel = profile.strategy === 'markdown' && markdownHeadingMode !== 0 ? 'Section max size' : 'Chunk size'

  const fields = [
    <Form.Item
      key="reader_strategy"
      name={['ingest_options', 'reader_strategy']}
      label={<HelpLabel label="Reader strategy" tooltip={tooltips.reader_strategy} />}
    >
      <Select allowClear placeholder="自动选择" options={readerStrategies} />
    </Form.Item>,
  ]

  if (profile.strategy === 'markdown') {
    fields.push(
      <Form.Item
        key="markdown_split_on_headings"
        preserve={false}
        name={['ingest_options', 'markdown_split_on_headings']}
        label={<HelpLabel label="Markdown heading split" tooltip={tooltips.markdown_split_on_headings} />}
      >
        <Select
          allowClear
          placeholder={`默认：${defaults?.markdown_split_on_headings ?? '按全部标题切分'}`}
          options={headingSplitOptions}
        />
      </Form.Item>,
      <NumberField
        key="chunk_size"
        name="chunk_size"
        label={chunkLabel}
        tooltip={tooltips.chunk_size}
        placeholder={defaults ? String(defaults.chunk_size) : '默认'}
        min={200}
      />,
      <NumberField
        key="chunk_overlap"
        name="chunk_overlap"
        label="Overlap"
        tooltip={tooltips.chunk_overlap}
        placeholder={defaults ? String(defaults.chunk_overlap) : '默认'}
        min={0}
      />
    )
  } else if (profile.strategy === 'csv_row') {
    fields.push(
      <SwitchField
        key="csv_skip_header"
        name="csv_skip_header"
        label="CSV skip header"
        tooltip={tooltips.csv_skip_header}
        defaultChecked={defaults?.csv_skip_header ? true : undefined}
      />,
      <SwitchField
        key="csv_clean_rows"
        name="csv_clean_rows"
        label="CSV clean rows"
        tooltip={tooltips.csv_clean_rows}
        defaultChecked={defaults?.csv_clean_rows ?? true}
      />
    )
  } else if (profile.strategy === 'code') {
    fields.push(
      <NumberField
        key="code_chunk_size"
        name="code_chunk_size"
        label="Code chunk size"
        tooltip={tooltips.code_chunk_size}
        placeholder={defaults ? String(defaults.code_chunk_size) : '默认'}
        min={256}
      />,
      <Form.Item
        key="code_tokenizer"
        preserve={false}
        name={['ingest_options', 'code_tokenizer']}
        label={<HelpLabel label="Code tokenizer" tooltip={tooltips.code_tokenizer} />}
      >
        <Select allowClear placeholder={`默认：${defaults?.code_tokenizer ?? 'character'}`} options={tokenizerOptions} />
      </Form.Item>,
      <SwitchField
        key="code_include_nodes"
        name="code_include_nodes"
        label="Include nodes"
        tooltip={tooltips.code_include_nodes}
        defaultChecked={defaults?.code_include_nodes ? true : undefined}
      />
    )
  } else if (profile.strategy === 'semantic') {
    fields.push(
      <NumberField
        key="chunk_size"
        name="chunk_size"
        label="Chunk size"
        tooltip={tooltips.chunk_size}
        placeholder={defaults ? String(defaults.chunk_size) : '默认'}
        min={200}
      />,
      <NumberField
        key="semantic_threshold"
        name="semantic_threshold"
        label="Semantic threshold"
        tooltip={tooltips.semantic_threshold}
        placeholder={defaults ? String(defaults.semantic_threshold) : '默认'}
        min={0}
        max={1}
        step={0.01}
      />,
      <NumberField
        key="semantic_similarity_window"
        name="semantic_similarity_window"
        label="Semantic window"
        tooltip={tooltips.semantic_similarity_window}
        placeholder={defaults ? String(defaults.semantic_similarity_window) : '3'}
        min={1}
      />,
      <NumberField
        key="semantic_min_sentences_per_chunk"
        name="semantic_min_sentences_per_chunk"
        label="Min sentences"
        tooltip={tooltips.semantic_min_sentences_per_chunk}
        placeholder={defaults ? String(defaults.semantic_min_sentences_per_chunk) : '1'}
        min={1}
      />,
      <NumberField
        key="semantic_min_characters_per_sentence"
        name="semantic_min_characters_per_sentence"
        label="Min chars per sentence"
        tooltip={tooltips.semantic_min_characters_per_sentence}
        placeholder={defaults ? String(defaults.semantic_min_characters_per_sentence) : '24'}
        min={1}
      />
    )
  } else {
    fields.push(
      <NumberField
        key="chunk_size"
        name="chunk_size"
        label="Chunk size"
        tooltip={tooltips.chunk_size}
        placeholder={defaults ? String(defaults.chunk_size) : '默认'}
        min={200}
      />,
      <NumberField
        key="chunk_overlap"
        name="chunk_overlap"
        label="Overlap"
        tooltip={tooltips.chunk_overlap}
        placeholder={defaults ? String(defaults.chunk_overlap) : '默认'}
        min={0}
      />
    )
  }

  return (
    <Collapse
      className="knowledge-advanced-options"
      ghost
      items={[
        {
          key: 'advanced',
          label: (
            <Space wrap>
              <span>高级分块参数</span>
              <Tag>{profile.label}</Tag>
              <Typography.Text type="secondary">{profile.description}</Typography.Text>
            </Space>
          ),
          children: <div className="knowledge-advanced-grid">{fields}</div>,
        },
      ]}
    />
  )
}
