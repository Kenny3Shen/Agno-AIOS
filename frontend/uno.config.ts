import {
  defineConfig,
  presetUno,
  transformerDirectives,
  transformerVariantGroup,
} from 'unocss'

export default defineConfig({
  dark: 'class',
  content: {
    filesystem: ['index.html', 'src/**/*.{vue,ts}'],
  },
  presets: [
    presetUno(),
  ],
  transformers: [transformerDirectives(), transformerVariantGroup()],
  theme: {
    colors: {
      security: {
        bg: '#071014',
        panel: '#0E171F',
        panel2: '#111D26',
        border: '#20313D',
        text: '#E6EDF3',
        muted: '#8EA0AE',
        blue: '#2F8FED',
        cyan: '#6AD7FF',
        green: '#54D38A',
        yellow: '#F6C343',
        red: '#F06A6A',
      },
    },
  },
  shortcuts: {
    'soc-card':
      'rounded-2 border border-[#D8E0E7] bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-[#20313D] dark:bg-[#0E171F]',
    'soc-muted': 'text-[#5F7080] dark:text-[#8EA0AE]',
    'soc-heading': 'text-[#111827] dark:text-[#E6EDF3]',
    'soc-focus': 'focus:outline-none focus-visible:ring-2 focus-visible:ring-[#6AD7FF] focus-visible:ring-offset-2 focus-visible:ring-offset-[#071014]',
    'ag-metric-chip':
      'inline-flex min-w-0 max-w-full items-center justify-between gap-2 rounded-[var(--ag-radius-control)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-[9px] py-[6px]',
    'ag-metric-label':
      'min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[11px] font-720 text-[var(--ag-muted)]',
    'ag-metric-value':
      'min-w-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[11px] font-760 text-[var(--ag-heading)]',
    'ag-status-chip':
      'inline-flex min-w-0 items-center justify-center gap-1.5 rounded-[var(--ag-radius-control)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-2 py-[5px] text-xs font-760 leading-none text-[var(--ag-muted-strong)] whitespace-nowrap',
    'ag-status-blue':
      'border-[color-mix(in_srgb,var(--ag-blue)_42%,var(--ag-border))] bg-[var(--ag-blue-soft)] text-[var(--ag-blue)]',
    'ag-status-green':
      'border-[color-mix(in_srgb,var(--ag-green)_42%,var(--ag-border))] bg-[var(--ag-green-soft)] text-[var(--ag-green)]',
    'ag-status-yellow':
      'border-[color-mix(in_srgb,var(--ag-yellow)_42%,var(--ag-border))] bg-[var(--ag-yellow-soft)] text-[var(--ag-yellow)]',
    'ag-status-red':
      'border-[color-mix(in_srgb,var(--ag-red)_42%,var(--ag-border))] bg-[var(--ag-red-soft)] text-[var(--ag-red)]',
    'ag-status-muted':
      'border-[var(--ag-border)] bg-[var(--ag-panel-soft)] text-[var(--ag-muted)]',
    'ag-data-chip':
      'inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-[var(--ag-radius-control)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-2 py-[5px] text-[11px] leading-none text-[var(--ag-muted-strong)]',
    'ag-status-dot':
      'inline-block size-2 shrink-0 rounded-full bg-[var(--ag-muted)] ring-2 ring-[var(--ag-panel)]',
    'ag-section-header':
      'flex min-w-0 items-start justify-between gap-3 border-b border-[var(--ag-border)] pb-2',
    'ag-surface-row':
      'min-w-0 rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-panel)] p-3 transition-colors hover:border-[color-mix(in_srgb,var(--ag-blue)_38%,var(--ag-border))] hover:bg-[var(--ag-blue-soft)]',
    'ag-field-label':
      'text-[11px] font-760 uppercase tracking-[0.08em] text-[var(--ag-muted)]',
    'ag-code-panel':
      'min-w-0 overflow-hidden rounded-[var(--ag-radius-panel)] border border-[var(--ag-border)] bg-[var(--ag-code-bg)] text-[var(--ag-code-text)]',
    'ag-empty-compact':
      'grid min-h-[88px] place-items-center rounded-[var(--ag-radius-panel)] border border-dashed border-[var(--ag-border)] bg-[var(--ag-panel-soft)] px-4 py-3 text-center text-xs text-[var(--ag-muted)]',
    'ag-empty-state':
      'grid min-h-[240px] place-items-center content-center gap-2.5 rounded-[var(--ag-radius-panel)] border border-dashed border-[var(--ag-border)] bg-[var(--ag-panel)] p-8 text-center text-xs text-[var(--ag-muted)]',
    'ag-empty-icon': 'text-[28px] text-[var(--ag-blue)]',
    'ag-panel-header': 'flex min-w-0 items-start justify-between gap-3',
    'ag-panel-header-copy': 'grid min-w-0 gap-1',
    'ag-panel-title':
      'min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[13px] font-760 leading-[1.35] text-[var(--ag-heading)]',
    'ag-panel-subtitle':
      'min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-xs leading-[1.45] text-[var(--ag-muted)]',
    'ag-icon-button-compact':
      'inline-grid size-8 place-items-center rounded-[var(--ag-radius-control)] border border-[var(--ag-border)] bg-[var(--ag-panel-soft)] text-[var(--ag-muted-strong)] transition-colors hover:border-[color-mix(in_srgb,var(--ag-blue)_42%,var(--ag-border))] hover:bg-[var(--ag-blue-soft)] hover:text-[var(--ag-blue)]',
  },
})
