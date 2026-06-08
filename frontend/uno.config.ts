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
  },
})
