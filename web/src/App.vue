<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from './i18n'

const { t, lang, toggle } = useI18n()
const route = useRoute()

// Order and labels mirror the mock. 'gate' is the AI 评估 entry: that is the
// measured quality table, and it stays a first-class route rather than a demo page.
const NAV = ['home', 'generate', 'workflows', 'tasks', 'models', 'library', 'batch', 'schedule', 'gate', 'logs']
const ROUTES = { home: '/', gate: '/gate', generate: '/generate', workflows: '/workflows',
                 tasks: '/tasks', models: '/models', library: '/library', batch: '/batch',
                 schedule: '/schedule', logs: '/logs' }
const active = computed(() => NAV.find((k) => ROUTES[k] === route.path) || 'home')
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="logo">◣</span>
        <strong>{{ t.app }}</strong>
      </div>
      <input class="search" :placeholder="t.search" />
      <div class="user">
        <button class="icon ghost" :title="t.langToggle" @click="toggle()">{{ lang === 'zh' ? '中' : 'EN' }}</button>
        <span class="chip">{{ t.brand.split('·')[0].trim() }}</span>
      </div>
    </header>

    <div class="body">
      <nav class="sidenav">
        <RouterLink v-for="k in NAV" :key="k" :to="ROUTES[k]" :class="{ on: active === k }">
          <span class="dot" />{{ t.nav[k] }}
        </RouterLink>
      </nav>
      <main class="content"><RouterView /></main>
    </div>
  </div>
</template>
