import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GitHub Pages 项目站点部署在 /<repo>/ 下；本地开发保持根路径。
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
