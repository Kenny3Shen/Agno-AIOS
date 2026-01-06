import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../source', // 设置输出目录为 ../source
    emptyOutDir: true, // 构建前清空输出目录
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
