<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { MarkerType, Panel, VueFlow, useVueFlow } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '../canvas.css'
import { api } from '../api'
import { useI18n } from '../i18n'
import FlowNode from '../components/FlowNode.vue'
import ParamPanel from '../components/ParamPanel.vue'
import Lightbox from '../components/Lightbox.vue'
import Select from '../components/Select.vue'
import NumberField from '../components/NumberField.vue'

const { t, lang } = useI18n()
const { zoomIn, zoomOut, fitView } = useVueFlow()

const models = ref(null)
const templates = ref([])
const flows = ref([])
const nodes = ref([])
const edges = ref([])
const flowId = ref(null)
const flowName = ref('')
const query = ref('')
const err = ref('')
const pageErr = ref('')
const run = ref(null)
const editing = ref(null)
const selEdge = ref(null)
const zoom = ref(null)
const dirty = ref(false)

let seq = 0
let timer = null

const nameOf = (tpl) => (lang.value === 'zh' ? tpl.name : tpl.name_en) || tpl.name
const clone = (o) => JSON.parse(JSON.stringify(o || {}))

const cats = computed(() => ['all', ...new Set(templates.value.map((x) => x.category))])
const cat = ref('all')
const palette = computed(() => templates.value.filter((x) => {
  if (cat.value !== 'all' && x.category !== cat.value) return false
  if (!query.value) return true
  const q = query.value.toLowerCase()
  return [x.name, x.name_en, x.desc, x.desc_en].join(' ').toLowerCase().includes(q)
}))

const running = computed(() => !!run.value && ['queued', 'running'].includes(run.value.state))
const busy = computed(() => running.value || !nodes.value.length)

const flowOptions = computed(() => flows.value.map((f) => ({
  value: String(f.id), label: `${f.name} · ${f.nodes}${t.value.canvasSteps}` }),
))
const opened = computed(() => (flowId.value ? String(flowId.value) : ''))

function add(tpl) {
  seq += 1
  const i = nodes.value.length
  nodes.value.push({
    id: `s${seq}`,
    type: 'step',
    position: { x: 16 + (i % 3) * 272, y: 24 + Math.floor(i / 3) * 232 },
    data: { tpl, params: clone(tpl.defaults), order: i + 1, run: null, changed: [], pickIdx: 0 },
  })
  dirty.value = true
  err.value = ''
  reframe()
}

// A chain is read left to right, so the canvas keeps the whole of it in view as steps come
// and go. Fitting waits for the library's own nodes-initialized signal: a card that has
// not been measured yet contributes nothing to the bounds, which is how a reopened canvas
// ended up pinned 14px from the left edge with 555px of dead stage on the right.
//
// maxZoom 1.1 is the other half: without it a three-step chain "fits" a 1250px stage by
// rendering at the viewport cap, i.e. every card 70% larger than designed. The buttons
// still zoom in further by hand.
function reframe() {
  nextTick(() => fitView({ padding: 0.08, maxZoom: 1.1, duration: 240 }))
}

// Opening the step drawer takes 420px from the stage, which would leave the tail of the
// chain behind the panel.
watch(editing, () => reframe())

function delNode(id) {
  nodes.value = nodes.value.filter((n) => n.id !== id)
  edges.value = edges.value.filter((e) => e.source !== id && e.target !== id)
  if (editing.value === id) editing.value = null
  dirty.value = true
  reframe()
}

function delEdge(id) {
  edges.value = edges.value.filter((e) => e.id !== id)
  selEdge.value = null
  dirty.value = true
}

// The library's own rule check, mirrored from flows.validate: a wire that cannot mean
// anything should never reach the canvas, rather than be drawn and then refused.
//
// Note the `e.id !== c.id` guard: isValidConnection is called again when an edge is
// written into the store, so without it a wire finds its own occupancy and is rejected
// as a duplicate of itself -- it never renders and the only trace is an EDGE_INVALID.
function canConnect(c) {
  if (!c.source || !c.target || c.source === c.target) return false
  const s = nodes.value.find((n) => n.id === c.source)
  const d = nodes.value.find((n) => n.id === c.target)
  if (!s || !d) return false
  const port = d.data.tpl.ports.in.find((p) => p.name === c.targetHandle)
  if (!port || port.type !== s.data.tpl.media) return false
  return !edges.value.some((e) => e.id !== c.id && e.target === c.target && e.targetHandle === c.targetHandle)
}

function onConnect(c) {
  if (!canConnect(c)) return
  edges.value = [...edges.value, mkEdge(c.source, c.sourceHandle, c.target, c.targetHandle, 0)]
  dirty.value = true
}

function mkEdge(source, sourceHandle, target, targetHandle, index) {
  return {
    id: `e-${source}-${sourceHandle}-${target}-${targetHandle}`,
    source, target, sourceHandle, targetHandle,
    type: 'smoothstep',
    data: { index },
    label: `#${index + 1}`,
    labelBgPadding: [4, 2], labelBorderRadius: 0,
    style: { stroke: '#2a3a5c', strokeWidth: 1.6 },
    markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#2a3a5c' },
  }
}

function onEdgeClick({ edge }) {
  selEdge.value = edge.id
  nodes.value.forEach((n) => (n.selected = false))
}

// The number on a wire is which output of the upstream step goes down it. The backend
// counts from 0; the label and the field count from 1, because that is what the result
// rail shows a person.
const pickedEdge = computed(() => edges.value.find((e) => e.id === selEdge.value) || null)
const pickedFrame = computed({
  get: () => (pickedEdge.value?.data.index ?? 0) + 1,
  set: (v) => {
    const e = pickedEdge.value
    if (!e) return
    e.data.index = Math.min(Math.max(0, Math.round(v) - 1), pickedMax.value - 1)
    e.label = `#${e.data.index + 1}`
    dirty.value = true
  },
})
const edgeEnds = computed(() => {
  const e = pickedEdge.value
  if (!e) return ''
  const s = nodes.value.find((n) => n.id === e.source)
  const d = nodes.value.find((n) => n.id === e.target)
  return `${nameOf(s.data.tpl)} → ${nameOf(d.data.tpl)}`
})

// The picker is bounded by what the upstream step actually produced, and names the file
// it points at: 「第 3 张」 is only meaningful against a run, and a slot can be a tombstone.
const pickedSource = computed(() => nodes.value.find((n) => n.id === pickedEdge.value?.source) || null)
const pickedOuts = computed(() => pickedSource.value?.data.run?.outputs || [])
const pickedMax = computed(() => pickedOuts.value.length || 9)
const pickedName = computed(() => {
  const o = pickedOuts.value[pickedEdge.value?.data.index ?? 0]
  return o ? (o.deleted ? t.value.deletedRun : o.filename) : ''
})

function decorate() {
  const byStep = new Map((run.value?.steps || []).map((s) => [s.node, s]))
  nodes.value.forEach((n, i) => {
    const d = n.data
    d.order = i + 1
    d.changed = Object.entries(d.params)
      .filter(([k, v]) => k !== 'prefix' && v !== d.tpl.defaults?.[k])
      .slice(0, 4)
      .map(([k, v]) => ({ k, v: typeof v === 'number' ? v : String(v).slice(0, 22) }))
    const out = edges.value.filter((e) => e.source === n.id)
    d.pickIdx = out.length ? Math.min(...out.map((e) => e.data.index ?? 0)) : 0
    d.run = byStep.get(n.id) || null
  })
  // A wire moves while the step at its far end is the one being waited on: that is the
  // difference between "this chain is working" and "the engine is stuck on a 90s clip".
  const live = (run.value?.steps || []).find((s) => ['queued', 'running'].includes(s.state))
  edges.value.forEach((e) => { e.animated = !!live && e.target === live.node })
}

// Watching the arrays themselves would re-fire on everything decorate writes; this
// signature leaves those fields out, so the pass runs once per authored change.
const authored = computed(() => [
  nodes.value.map((n) => `${n.id}|${JSON.stringify(n.data.params)}`).join('#'),
  edges.value.map((e) => `${e.source}>${e.target}:${e.targetHandle}:${e.data.index}`).join('#'),
].join('||'))
watch(authored, decorate)

function toGraph() {
  return {
    nodes: nodes.value.map((n) => ({
      id: n.id, template: n.data.tpl.id, params: n.data.params,
      position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
    })),
    edges: edges.value.map((e) => ({
      from: e.source, out: e.sourceHandle, to: e.target, in: e.targetHandle, index: e.data.index ?? 0,
    })),
  }
}

function fromGraph(g, tplById) {
  nodes.value = (g.nodes || []).map((n) => {
    const tpl = tplById[n.template]
    return { id: n.id, type: 'step', position: { ...n.position },
             data: { tpl, params: { ...clone(tpl.defaults), ...n.params }, order: 0, run: null,
                     changed: [], pickIdx: 0 } }
  })
  edges.value = (g.edges || []).map((e) => mkEdge(e.from, e.out, e.to, e.in, e.index ?? 0))
}

async function loadFlows() {
  flows.value = (await api.flows()).flows
}

async function open(id) {
  if (!id) return
  const f = await api.flow(Number(id))
  flowId.value = f.id
  flowName.value = f.name
  fromGraph(f.graph, Object.fromEntries(templates.value.map((x) => [x.id, x])))
  run.value = null
  err.value = ''
  dirty.value = false
  if (f.runs?.length) {
    run.value = await api.flowRun(f.runs[0].run)
    decorate()
  }
}

watch(opened, (v) => { if (v && String(flowId.value) !== v) open(v) })

function fresh() {
  flowId.value = null
  flowName.value = ''
  nodes.value = []
  edges.value = []
  run.value = null
  err.value = ''
  dirty.value = false
}

async function save() {
  err.value = ''
  if (!nodes.value.length) { err.value = t.value.canvasEmpty; return false }
  if (!flowName.value.trim()) { err.value = t.value.canvasNeedName; return false }
  const body = { name: flowName.value.trim(), graph: toGraph() }
  try {
    if (flowId.value) await api.updateFlow(flowId.value, body)
    else flowId.value = (await api.createFlow(body)).flow_id
    dirty.value = false
    await loadFlows()
    return true
  } catch (e) {
    // The refusal is the structural rule the canvas cannot check locally -- a cycle,
    // or a template that has left the registry. It comes back as a sentence, so it goes
    // on screen as one.
    err.value = e.message
    return false
  }
}

async function go() {
  if (!(await save())) return
  run.value = null
  try {
    const r = await api.runFlow(flowId.value)
    stop()
    timer = setInterval(poll, 1500)
    await poll(r.run)
  } catch (e) {
    err.value = e.message
  }
}

async function poll(ref) {
  const st = await api.flowRun(ref || run.value?.run)
  run.value = st
  decorate()
  if (['done', 'error'].includes(st.state)) stop()
}

function stop() {
  if (timer) clearInterval(timer)
  timer = null
}

const editingNode = computed(() => nodes.value.find((n) => n.id === editing.value) || null)

function onZoom({ shot }) {
  const files = shot.all
  zoom.value = { files, index: Math.max(0, files.findIndex((f) => f.filename === shot.filename)) }
}

async function boot() {
  try {
    const [m, tp] = await Promise.all([api.models(), api.templates()])
    models.value = m
    templates.value = tp.templates
    await loadFlows()
  } catch (e) {
    pageErr.value = e.message
  }
}
boot()
onBeforeUnmount(stop)
</script>

<template>
  <div class="page fill">
    <header class="pagehead">
      <h1>{{ t.nav.canvas }}</h1>
      <p>{{ t.canvasSub }}</p>
    </header>
    <p v-if="pageErr" class="drift">{{ pageErr }}</p>

    <div class="flowbar">
      <input v-model="flowName" class="namei" :placeholder="t.canvasNameHint" maxlength="120" />
      <span class="saved"><Select :model-value="opened" :options="flowOptions" :label="t.canvasSaved"
                                  @update:model-value="open($event)" /></span>
      <button class="ghost" @click="fresh">{{ t.canvasNew }}</button>
      <button class="ghost" :disabled="!dirty" @click="save">{{ t.canvasSave }}</button>
      <button class="go" :disabled="busy" @click="go">
        ▶ {{ running ? t.canvasRunning : t.canvasRun }}
      </button>
      <span v-if="run" class="rstate" :class="run.state">
        <i class="dot" />{{ t.canvasState[run.state] }}
        <b v-if="run.error" class="rerr">{{ run.error }}</b>
      </span>
    </div>
    <p v-if="err" class="drift">{{ err }}</p>

    <div class="flowpage" :class="{ drawer: !!editingNode }">
      <aside class="palette">
        <div class="phead">{{ t.canvasPalette }}</div>
        <input v-model="query" class="mini" :placeholder="t.search" />
        <div class="pchips">
          <button v-for="c in cats" :key="c" class="ghost sm" :class="{ on: cat === c }" @click="cat = c">
            {{ c === 'all' ? t.categoryAll : t.categories[c] || c }}
          </button>
        </div>
        <div class="palist">
          <button v-for="x in palette" :key="x.id" class="prow" :title="x.desc" @click="add(x)">
            <span class="pn">{{ nameOf(x) }}</span>
            <span class="pm">{{ x.ports.in.length ? t.canvasJoinable : t.canvasStarts }}</span>
          </button>
          <p v-if="!palette.length" class="pnone">{{ t.noRunsOf }}</p>
        </div>
      </aside>

      <div class="stage">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :is-valid-connection="canConnect"
          :delete-key-code="null"
          :snap-to-grid="true"
          :snap-grid="[8, 8]"
          :min-zoom="0.2"
          :max-zoom="2"
          :default-viewport="{ zoom: 0.85 }"
          @connect="onConnect"
          @nodes-initialized="reframe"
          @edge-click="onEdgeClick"
          @pane-click="selEdge = null"
          @node-click="({ node }) => (editing = node.id)"
        >
          <template #node-step="p">
            <FlowNode :id="p.id" :data="p.data" :selected="p.selected"
                      @edit="editing = $event" @del="delNode" @zoom="onZoom" />
          </template>

          <Panel position="bottom-left" class="zoomer">
            <button class="zb" :title="t.canvasZoomIn" @click="zoomIn()">＋</button>
            <button class="zb" :title="t.canvasZoomOut" @click="zoomOut()">－</button>
            <button class="zb" :title="t.canvasFit" @click="reframe()">▣</button>
          </Panel>

          <Panel v-if="pickedEdge" position="top-center" class="wire">
            <span class="wt">{{ edgeEnds }}</span>
            <label class="wl">{{ t.canvasFrame }}
              <NumberField v-model="pickedFrame" :min="1" :max="pickedMax" :label="t.canvasFrame" />
            </label>
            <span v-if="pickedName" class="wf">{{ pickedName }}</span>
            <button class="ghost sm" @click="delEdge(pickedEdge.id)">{{ t.canvasDelWire }}</button>
            <button class="ghost sm" :title="t.close" @click="selEdge = null">✕</button>
          </Panel>
        </VueFlow>
        <p v-if="!nodes.length" class="hint0">{{ t.canvasEmptyHint }}</p>
      </div>

      <ParamPanel v-if="editingNode" :template="editingNode.data.tpl" :params="editingNode.data.params"
                  :models="models?.catalog" :err="err" :show-run="false"
                  @close="editing = null" @del="editing && delNode(editing)" />
    </div>

    <Lightbox v-if="zoom" :title="t.variants" :code="''" :files="zoom.files" :index="zoom.index"
              @close="zoom = null" @update:index="zoom.index = $event" />
  </div>
</template>
