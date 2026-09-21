<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({ tasks: Array, names: Object, active: Number })
const emit = defineEmits(['pick'])
const { t } = useI18n()

const TABS = { all: 'tabAll', running: 'tabRunning', done: 'tabDone', failed: 'tabFailed' }
const tab = ref('all')

// The list endpoint caps at 200 rows and has no offset, so the paging is over what
// the page already holds -- enough for the run history this box actually shows.
const PER = 10
const page = ref(1)
const filtered = computed(() => props.tasks.filter((x) => {
  if (tab.value === 'all') return true
  if (tab.value === 'running') return ['queued', 'running'].includes(x.state)
  if (tab.value === 'failed') return x.state === 'error'
  return x.state === 'done'
}))
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / PER)))
const shown = computed(() => filtered.value.slice((page.value - 1) * PER, page.value * PER))

watch(tab, () => { page.value = 1 })
watch(pages, (n) => { if (page.value > n) page.value = n })

// Rendered from whichever keys this task actually carries: an image run has no
// length and a video run has no batch, and a fixed template showed "undefined步"
// for one of the two.
const UNITS = { width: 'w', height: 'h', steps: '步', cfg: 'cfg', seed: 'seed', batch: '张', length: '帧', fps: 'fps', octree: 'oct' }
function params(x) {
  const p = x.params || {}
  if (p.width && p.height) return `${p.width}×${p.height} · ${p.steps ?? '?'}步` + (p.length ? ` · ${p.length}帧` : '')
  return Object.keys(p).map((k) => `${UNITS[k] || k}=${p[k]}`).join(' ') || '—'
}
function stamp(iso) {
  return iso ? new Date(iso + 'Z').toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
}
</script>

<template>
  <section class="card">
    <div class="rtabs">
      <button v-for="(lbl, k) in TABS" :key="k" class="ghost sm" :class="{ on: tab === k }" @click="tab = k">
        {{ t[lbl] }}
      </button>
    </div>
    <p v-if="!shown.length" class="hint">{{ t.emptyTasks }}</p>
    <div v-else class="tscroll">
      <table class="tasks">
        <thead>
          <tr>
            <th>{{ t.th.ref }}</th><th>{{ t.th.template }}</th><th>{{ t.th.model }}</th>
            <th>{{ t.th.params }}</th><th>{{ t.th.state }}</th><th>{{ t.th.created }}</th>
            <th class="ops-col">{{ t.th.actions }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="x in shown" :key="x.id" :class="{ on: x.id === active }">
            <td class="mono">{{ x.ref }}</td>
            <td>{{ names?.[x.template] || x.template }}</td>
            <td class="muted">{{ x.model }}</td>
            <td class="mono">{{ params(x) }}</td>
            <td><span class="chip" :class="x.state">{{ t.state[x.state] || x.state }}</span></td>
            <td class="mono">{{ stamp(x.created_at) }}</td>
            <td class="ops"><button class="ghost sm" @click="emit('pick', x)">{{ t.view }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="pages > 1" class="pager">
      <button class="ghost sm" :disabled="page === 1" :title="t.prevPage" @click="page--">‹</button>
      <span class="mono">{{ page }} / {{ pages }}</span>
      <button class="ghost sm" :disabled="page === pages" :title="t.nextPage" @click="page++">›</button>
      <span class="hint">{{ t.rowsTotal }} {{ filtered.length }} · {{ t.perPage }} {{ PER }}</span>
    </div>
  </section>
</template>
