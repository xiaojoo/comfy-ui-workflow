<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '../api'
import { useI18n } from '../i18n'
import TaskTable from '../components/TaskTable.vue'
import TaskDetail from '../components/TaskDetail.vue'

const { t } = useI18n()

const tasks = ref([])
const templates = ref([])
const detail = ref(null)
const err = ref('')

const names = computed(() => Object.fromEntries(templates.value.map((y) => [y.id, y.name])))
const nameOf = (x) => names.value[x.template] || x.template

async function show(id) {
  try { detail.value = await api.task(id) }
  catch { /* engine restarting; the next tick re-reads it */ }
}

async function refresh() {
  try {
    tasks.value = (await api.tasks(200)).tasks
    err.value = ''
    // The list rows carry no log, outputs or full parameter set, so an open drawer is
    // re-read rather than patched from the row -- and it stops once the task settles.
    if (detail.value && ['queued', 'running'].includes(detail.value.state)) await show(detail.value.id)
  } catch (e) {
    err.value = `${e.status ?? ''} ${e.message}`
  }
}
async function boot() {
  try { templates.value = (await api.templates()).templates } catch { /* the id shows instead */ }
}
refresh()
boot()
const timer = setInterval(refresh, 2000)
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="page">
    <header class="pagehead">
      <h1>{{ t.nav.tasks }}</h1>
      <p>{{ t.tasksSubtitle }}</p>
    </header>
    <p v-if="err" class="drift">{{ err }}</p>

    <div class="split" :class="{ open: !!detail }">
      <TaskTable :tasks="tasks" :names="names" :active="detail?.id" @pick="(x) => show(x.id)" />
      <TaskDetail v-if="detail" :task="detail" :name="nameOf(detail)" @close="detail = null" />
    </div>
  </div>
</template>
