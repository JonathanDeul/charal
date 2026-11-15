import { env } from 'node:process'
import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2026-11-14',
  ssr: false,
  devtools: { enabled: false },
  css: ['~/assets/main.css', 'leaflet/dist/leaflet.css'],
  vite: {
    plugins: [tailwindcss()],
    server: { proxy: { '/api': env.API_PROXY_TARGET || 'http://127.0.0.1:8000' } }
  },
  app: {
    head: {
      title: 'Charal — California Fire Observatory',
      meta: [{ name: 'description', content: 'A continuous view of California fire activity. Explore NASA MODIS and VIIRS observations, sensor harmonization, and the statistics of extreme fires.' }],
      link: [{ rel: 'icon', type: 'image/svg+xml', href: '/favicon.svg' }]
    }
  },
  typescript: { strict: true }
})
