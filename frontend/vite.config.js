import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// Сборка кладётся прямо в web/static: FastAPI раздаёт её тем же процессом,
// поэтому в проде один origin и куки-авторизация без CORS.
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  // Локально собираем сразу в web/static (его раздаёт FastAPI), а в Docker-стадии
  // задаём VITE_OUT_DIR=dist: внутри образа исходники лежат в /ui, и «../web/static»
  // оказалось бы вне рабочей папки — оттуда копировать нечего.
  build: {
    outDir: process.env.VITE_OUT_DIR || '../web/static',
    emptyOutDir: true,
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8080', changeOrigin: false } },
  },
})
