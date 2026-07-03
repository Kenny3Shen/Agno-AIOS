import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), UnoCSS()],
  build: {
    outDir: '../source',
    emptyOutDir: true,
    chunkSizeWarningLimit: 3500,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('/vue/') || id.includes('/pinia/') || id.includes('/vue-i18n/')) return 'vue'
          if (id.includes('/element-plus/') || id.includes('/@element-plus/icons-vue/')) return 'element'
          if (id.includes('/markdown-it/') || id.includes('/highlight.js/')) return 'markdown'
          if (id.includes('/mermaid/')) return 'mermaid'
          return 'vendor'
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
    watch: {
      ignored: ['**/node_modules/**', '**/logs/**', '**/.git/**', '**/dist/**', '**/frontend/.cache/**'],
    },
  },
})
