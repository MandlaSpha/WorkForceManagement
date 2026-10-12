import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import './styles/index.css'
import App from './App.vue'
import { createAppRouter } from './router'

const app = createApp(App)
app.use(createPinia())
app.use(VueQueryPlugin)
app.use(createAppRouter())
app.mount('#app')
