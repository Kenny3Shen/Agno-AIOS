import tailwindcss from '@tailwindcss/vite'
import viteReact from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  resolve: { tsconfigPaths: true },
  build: {
    emptyOutDir: true,
    outDir: '../source',
  },
  plugins: [tailwindcss(), viteReact()],
})
