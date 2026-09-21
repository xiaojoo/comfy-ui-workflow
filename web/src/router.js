import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Gate from './views/Gate.vue'
import Placeholder from './views/Placeholder.vue'

// Only two routes carry real function in this build. The other nav entries exist
// because the shell needs them, and each renders an explicit "not implemented"
// state rather than an empty-looking page or invented content.
const todo = (key) => ({ path: '/' + key, component: Placeholder, props: { navKey: key } })

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/gate', component: Gate },
    todo('generate'), todo('workflows'), todo('tasks'), todo('models'),
    todo('library'), todo('batch'), todo('schedule'), todo('logs'),
  ],
})
