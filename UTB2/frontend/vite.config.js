import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  server: { proxy: { '/api': 'http://127.0.0.1:8001' } },
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png', 'masked-icon.svg'],
      manifest: {
        name: 'Расписание okak.asia',
        short_name: 'okak.asia',
        description: 'Удобное расписание занятий университета',
        theme_color: '#ffffff',
        background_color: '#ffffff',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: '/logo-192-192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: '/logo-512-512.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            src: '/logo-512-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable'
          }
        ]
      },
      workbox: {
        // Кэшируем статику (JS, CSS, HTML, картинки)
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // Official schedules must reflect the latest publication, including removals.
        runtimeCaching: [{
          urlPattern: ({ url }) => url.pathname.startsWith('/api/v1/'),
          handler: 'NetworkOnly',
        }]
      }
    })
  ]
})