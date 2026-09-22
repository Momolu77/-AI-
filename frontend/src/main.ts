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
        themes: { light: { colors: { primary: '#24664f', secondary: '#b16d35' } } },
      },
    }),
  )
  .mount('#app')
