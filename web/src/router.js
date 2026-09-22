import { createRouter, createWebHistory } from 'vue-router'
import Workflows from './views/Workflows.vue'
import Tasks from './views/Tasks.vue'
import Gate from './views/Gate.vue'
import Placeholder from './views/Placeholder.vue'

// The routes below carry real function. The other nav entries exist because the shell
// needs them, and each renders an explicit "not implemented" state rather than an
// empty-looking page or invented content.
const todo = (key) => ({ path: '/' + key, component: Placeholder, props: { navKey: key } })

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Workflows },
    // Loaded on demand: the canvas drags a graph editor with it, and the other three
    // pages should not pay for it at first paint.
    { path: '/canvas', component: () => import('./views/Canvas.vue') },
    { path: '/tasks', component: Tasks },
    { path: '/gate', component: Gate },
    todo('models'), todo('library'), todo('batch'), todo('schedule'), todo('logs'),
  ],
})
