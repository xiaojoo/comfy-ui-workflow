<script setup>
import { computed, ref } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({ tasks: Array })
const emit = defineEmits(['pick'])
const { t } = useI18n()

const TABS = { all: 'tabAll', running: 'tabRunning', done: 'tabDone', failed: 'tabFailed' }
const tab = ref('all')

const shown = computed(() => props.tasks.filter((x) => {
  if (tab.value === 'all') return true
  if (tab.value === 'running') return ['queued', 'running'].includes(x.state)
  if (tab.value === 'failed') return x.state === 'error'
  return x.state === 'done'
}))

function params(x) {
  const p = x.params || {}
  if (!p.width) return '—'
  return `${p.width}×${p.height} / ${p.steps}步`
}
function stamp(iso) {
  return iso ? new Date(iso + 'Z').toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
}
</script>

<template>
  <section class="card">
    <h2>{{ t.recent }}
      <span class="tabs">
        <button v-for="(lbl, k) in TABS" :key="k" class="ghost sm" :class="{ on: tab === k }" @click="tab = k">
          {{ t[lbl] }}
        </button>
      </span>
    </h2>
    <p v-if="!shown.length" class="hint">{{ t.emptyTasks }}</p>
    <table v-else class="tasks">
      <thead>
        <tr>
          <th>{{ t.th.ref }}</th><th>{{ t.th.template }}</th><th>{{ t.th.model }}</th>
          <th>{{ t.th.params }}</th><th>{{ t.th.state }}</th><th>{{ t.th.created }}</th><th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="x in shown" :key="x.id">
          <td class="mono">{{ x.ref }}</td>
          <td>{{ x.title || x.template }}</td>
          <td class="muted">{{ x.model }}</td>
          <td class="mono">{{ params(x) }}</td>
          <td><span class="chip" :class="x.state">{{ t.state[x.state] || x.state }}</span></td>
          <td class="mono">{{ stamp(x.created_at) }}</td>
          <td><button class="ghost sm" @click="emit('pick', x)">{{ t.view }}</button></td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
