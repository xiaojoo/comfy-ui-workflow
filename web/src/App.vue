<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from './api'
import { useI18n } from './i18n'
import GateTable from './components/GateTable.vue'
import Preview from './components/Preview.vue'

const { t, lang, toggle } = useI18n()
const health = ref(null)
const batches = ref([])
const gate = ref(null)
const selectedId = ref(null)
const assetId = ref(null)
const busy = ref(false)
const notice = ref('')
const draft = ref({ name: '', rows: [{ name: '', source_png: '', raw_svg: '' }] })

const open = computed(() => batches.value.filter((b) => b.state === 'queued' || b.state === 'running').length)
const asset = computed(() => gate.value?.rows.find((r) => r.id === assetId.value) || null)

async function refreshBatches() {
  try {
    batches.value = (await api.batches()).batches
    if (selectedId.value === null && batches.value.length) select(batches.value[0].batch_id)
  } catch (e) { notice.value = e.message }
}

async function select(id) {
  selectedId.value = id
  assetId.value = null
  try {
    gate.value = await api.gate(id)
    if (!assetId.value && gate.value.rows.length) assetId.value = gate.value.rows[0].id
  } catch (e) { gate.value = null; notice.value = e.message }
}

async function submit() {
  const rows = draft.value.rows.filter((r) => r.source_png && r.raw_svg)
  if (!draft.value.name.trim()) { notice.value = t.value.needName; return }
  if (!rows.length) { notice.value = t.value.needRows; return }
  busy.value = true
  notice.value = ''
  try {
    const r = await api.create({ name: draft.value.name.trim(), items: rows })
    notice.value = `#${r.batch_id} · ${r.assets} assets · queue ${r.queue_position}`
    await refreshBatches()
    select(r.batch_id)
  } catch (e) { notice.value = e.message } finally { busy.value = false }
}

async function approve({ id, approve }) {
  try {
    await api.approve(selectedId.value, id, approve)
    gate.value = await api.gate(selectedId.value)
  } catch (e) { notice.value = `${e.status} ${e.message}` }
}

function addRow() { draft.value.rows.push({ name: '', source_png: '', raw_svg: '' }) }
function delRow(i) { draft.value.rows.splice(i, 1) }

// A serial queue means the only way to know a batch finished is to ask. One
// interval covers both panes; it idles itself when nothing is in flight.
let timer = null
async function tick() {
  if (!open.value && gate.value?.state === 'done') return
  await refreshBatches()
  if (selectedId.value !== null && gate.value && !['done', 'error'].includes(gate.value.state)) {
    gate.value = await api.gate(selectedId.value)
  }
}

// Named rather than an IIFE: a statement that starts with "(" gets parsed as a call
// on the previous line when there is no semicolon, which silently killed setup here.
async function boot() {
  try { health.value = await api.health() } catch { health.value = { ok: false } }
  await refreshBatches()
  timer = setInterval(tick, 900)
}

boot()
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="shell">
    <header class="top">
      <div>
        <h1>{{ t.title }}</h1>
        <p class="sub">{{ t.subtitle }}</p>
      </div>
      <div class="meta">
        <span class="chip" :class="health?.ok ? 'ok-text' : 'fail'">
          {{ t.health }}: {{ health?.ok ? t.ok : t.degraded }}
        </span>
        <span v-if="health?.queued_ahead" class="chip">{{ t.queuedAhead }} {{ health.queued_ahead }}</span>
        <span v-if="open" class="chip running">{{ open }} {{ t.state.running }}</span>
        <button class="ghost" @click="toggle()">{{ t.langToggle }}</button>
      </div>
    </header>

    <main class="grid">
      <aside>
        <section class="card">
          <h2>{{ t.newBatch }}</h2>
          <label>{{ t.batchName }}<input v-model="draft.name" :placeholder="t.batchName" /></label>
          <div v-for="(r, i) in draft.rows" :key="i" class="row">
            <input v-model="r.name" placeholder="name" />
            <input v-model="r.source_png" :placeholder="t.sourcePng" />
            <input v-model="r.raw_svg" :placeholder="t.rawSvg" />
            <button class="ghost sm" @click="delRow(i)">{{ t.removeRow }}</button>
          </div>
          <div class="actions">
            <button class="ghost" @click="addRow">{{ t.addRow }}</button>
            <button :disabled="busy" @click="submit">{{ busy ? t.submitting : t.submit }}</button>
          </div>
          <p class="hint">{{ t.itemsHint }}</p>
          <p v-if="notice" class="notice">{{ notice }}</p>
        </section>

        <section class="card">
          <h2>{{ t.batches }}<button class="ghost sm" @click="refreshBatches">{{ t.refresh }}</button></h2>
          <p v-if="!batches.length" class="hint">{{ t.noBatches }}</p>
          <ul class="list">
            <li v-for="b in batches" :key="b.batch_id" :class="{ on: b.batch_id === selectedId }"
                @click="select(b.batch_id)">
              <span class="chip" :class="b.state">{{ t.state[b.state] || b.state }}</span>
              <strong>#{{ b.batch_id }} {{ b.name }}</strong>
              <span class="count">{{ b.passed }}/{{ b.assets }}</span>
              <span v-if="b.approved" class="count ap">{{ b.approved }} {{ t.approval.approved }}</span>
            </li>
          </ul>
        </section>
      </aside>

      <section class="card wide">
        <div v-if="!gate" class="empty">{{ selectedId ? t.loading : t.selectBatch }}</div>
        <template v-else>
          <h2>#{{ selectedId }} · {{ gate.summary }}
            <span class="chip" :class="gate.state">{{ t.state[gate.state] || gate.state }}</span>
          </h2>
          <GateTable :gate="gate" :selected="assetId" @select="assetId = $event.id" @approve="approve" />
          <Preview :batch-id="selectedId" :asset="asset" />
        </template>
      </section>
    </main>
  </div>
</template>
