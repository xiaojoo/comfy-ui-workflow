<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from './i18n'
import EngineStatus from './components/EngineStatus.vue'

const { t, lang, toggle } = useI18n()
const route = useRoute()

// The nav mirrors the mock's eight entries. Only the first two carry real function
// in this build; the rest render an explicit "not implemented" state.
const NAV = ['workflows', 'canvas', 'tasks', 'models', 'library', 'batch', 'schedule', 'gate', 'logs']
const ROUTES = { workflows: '/', canvas: '/canvas', tasks: '/tasks', models: '/models', library: '/library',
                 batch: '/batch', schedule: '/schedule', gate: '/gate', logs: '/logs' }
const active = computed(() => NAV.find((k) => ROUTES[k] === route.path) || 'workflows')

const ICONS = {
  workflows: '<rect x="2" y="2" width="5" height="5" rx="1.2"/><rect x="9" y="2" width="5" height="5" rx="1.2"/><rect x="2" y="9" width="5" height="5" rx="1.2"/><rect x="9" y="9" width="5" height="5" rx="1.2"/>',
  canvas: '<rect x="1.6" y="2.2" width="4.2" height="4.2" rx=".9"/><rect x="1.6" y="9.6" width="4.2" height="4.2" rx=".9"/><rect x="10.2" y="5.9" width="4.2" height="4.2" rx=".9"/><path d="M5.8 4.3c2.3 0 2.1 3.6 4.4 3.7M5.8 11.7c2.3 0 2.1-3.6 4.4-3.7"/>',
  tasks: '<circle cx="8" cy="8" r="6"/><path d="M8 4.6V8l2.6 1.6"/>',
  models: '<path d="M8 1.8 14 5v6l-6 3.2L2 11V5z"/><path d="M2 5l6 3.2L14 5M8 8.2v6"/>',
  library: '<path d="M2 5.4 8 2.4l6 3-6 3z"/><path d="M2 8.6l6 3 6-3"/>',
  batch: '<rect x="5.5" y="5.5" width="8.5" height="8.5" rx="1.5"/><path d="M10.5 5.5V3A1.5 1.5 0 0 0 9 1.5H3A1.5 1.5 0 0 0 1.5 3v6A1.5 1.5 0 0 0 3 10.5h2.5"/>',
  schedule: '<rect x="2" y="3.2" width="12" height="10.8" rx="1.5"/><path d="M2 6.6h12M5.4 1.6v2.6M10.6 1.6v2.6"/>',
  gate: '<path d="M8 1.8 13.4 4v4.2c0 3-2.3 5-5.4 6.1-3.1-1.1-5.4-3.1-5.4-6.1V4z"/><path d="M5.6 7.8 7.4 9.6l3.1-3.4"/>',
  logs: '<path d="M5.5 4h8M5.5 8h8M5.5 12h8"/><circle cx="2.8" cy="4" r=".95"/><circle cx="2.8" cy="8" r=".95"/><circle cx="2.8" cy="12" r=".95"/>',
}
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <img class="logo" src="/logo.svg" alt="" width="22" height="22" />
        <strong>{{ t.app }}</strong>
      </div>
      <button class="icon ghost" :title="t.langToggle" @click="toggle()">{{ lang === 'zh' ? '中' : 'EN' }}</button>
    </header>

    <div class="body">
      <nav class="sidenav">
        <div class="navlist">
          <RouterLink v-for="k in NAV" :key="k" :to="ROUTES[k]" :class="{ on: active === k }">
            <svg class="ico" viewBox="0 0 16 16" aria-hidden="true" v-html="ICONS[k]" />
            {{ t.nav[k] }}
          </RouterLink>
        </div>
        <EngineStatus />
      </nav>
      <main class="content"><RouterView /></main>
    </div>
  </div>
</template>
