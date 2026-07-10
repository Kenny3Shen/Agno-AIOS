import { defineConfig, presetUno, transformerDirectives, transformerVariantGroup } from 'unocss'

export default defineConfig({
  content: { filesystem: ['index.html', 'src/**/*.{ts,tsx}'] },
  presets: [presetUno()],
  transformers: [transformerDirectives(), transformerVariantGroup()],
})
