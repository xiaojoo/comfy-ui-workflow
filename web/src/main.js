import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './styles.css'
import './tooltip.js'
import './formnames.js'

createApp(App).use(router).mount('#app')
