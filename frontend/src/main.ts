import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import { VApp, VDialog, VBtn } from 'vuetify/components'
import 'vuetify/styles'
import './style.css'
import App from './App.vue'
createApp(App)
  .use(createPinia())
  .use(
    createVuetify({
      components: { VApp, VDialog, VBtn },
      theme: {
        defaultTheme: 'light',
        themes: {
          light: {
            colors: {
              primary: '#4f46e5', secondary: '#475569', background: '#f8fafc',
              surface: '#ffffff', error: '#b91c1c', success: '#15803d', warning: '#92400e',
            },
          },
        },
      },
    }),
  )
  .mount('#app')
