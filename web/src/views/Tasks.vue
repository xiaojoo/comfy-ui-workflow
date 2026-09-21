<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useI18n } from '../i18n'
import TaskTable from '../components/TaskTable.vue'

const { t } = useI18n()
const router = useRouter()

const tasks = ref([])
const err = ref('')

async function refresh() {
  try {
    tasks.value = (await api.tasks(200)).tasks
    err.value = ''
  } catch (e) {
    err.value = `${e.status ?? ''} ${e.message}`
  }
}
refresh()
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
    <TaskTable :tasks="tasks" @pick="(x) => router.push({ path: '/', query: { task: x.id } })" />
  </div>
</template>
