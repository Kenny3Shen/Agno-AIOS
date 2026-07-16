import { AutoComplete, Input, Typography } from 'antd'
import { useMemo, useState } from 'react'
import { celHintsFor, filterCelHints, type CelHint } from './celHints'

type Mode = 'condition' | 'loop' | 'router'

type Props = {
  value?: string
  onChange: (value: string) => void
  mode: Mode
  rows?: number
  placeholder?: string
  /** Anchor for dropdown (studio root). Defaults to body. */
  getPopupContainer?: (node: HTMLElement) => HTMLElement
}

export function CelExpressionField({
  value = '',
  onChange,
  mode,
  rows = 3,
  placeholder,
  getPopupContainer,
}: Props) {
  const [open, setOpen] = useState(false)
  const options = useMemo(() => {
    const hints = filterCelHints(celHintsFor(mode), value)
    return hints.map((hint: CelHint) => ({
      value: hint.value,
      label: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Typography.Text code style={{ fontSize: 12 }}>
            {hint.label}
          </Typography.Text>
          {hint.detail ? (
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {hint.detail}
            </Typography.Text>
          ) : null}
        </div>
      ),
    }))
  }, [mode, value])

  return (
    <AutoComplete
      className="nodrag nowheel nopan"
      style={{ width: '100%', marginTop: 4 }}
      options={options}
      open={open}
      onOpenChange={setOpen}
      value={value}
      onChange={(next) => onChange(String(next ?? ''))}
      onSelect={(next) => {
        onChange(String(next ?? ''))
        setOpen(false)
      }}
      getPopupContainer={
        getPopupContainer ??
        ((node) =>
          (node.closest('.workflow-studio') as HTMLElement | null) ?? document.body)
      }
    >
      <Input.TextArea
        rows={rows}
        placeholder={placeholder}
        className="nodrag nowheel nopan"
        onWheel={(e) => e.stopPropagation()}
      />
    </AutoComplete>
  )
}
