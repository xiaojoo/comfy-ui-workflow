<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { MarkerType, Panel, SelectionMode, VueFlow, useVueFlow } from '@vue-flow/core'
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
// The store handle, not just the helpers: alignment needs each node's measured box
// (`dimensions`) and its resolved flow position (`computedPosition`), which the model
// array we author does not carry.
const vf = useVueFlow()
const { zoomIn, zoomOut, fitView } = vf

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
// True between "the cards were swapped in" and "the viewport has been fitted to them".
const fitting = ref(false)
let fitNow = false
const stageEl = ref(null)

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

const running = computed(() => !!run.value && ['queued', 'running', 'cancelling'].includes(run.value.state))
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
  const instant = fitNow
  fitNow = false
  nextTick(() => {
    fitView({ padding: 0.08, maxZoom: 1.1, ...(instant ? {} : { duration: 240 }) })
    if (instant) fitting.value = false
  })
}

// Opening a saved canvas used to show the chain in the top-left corner for ~180ms and then
// slide it to the centre: the fit can only run once the library has measured the cards, and
// the tween that then moves the viewport is what reads as a stutter. On reopen the same fit
// runs without a tween, and the cards stay hidden until it has landed.
function refit() {
  fitting.value = true
  fitNow = true
  // If the library's measurement signal never arrives (a canvas with no cards, a reopen of
  // the one already on screen), show the stage rather than leave it blank -- and let the
  // next ordinary fit animate again.
  setTimeout(() => { fitting.value = false; fitNow = false }, 600)
}

// ------------------------------------------------------------------ alignment
// The bounds are the union of the selected cards' measured boxes, so aligning is
// "flush to the group's own edge", not to an invisible grid -- which is what a chain
// dragged by hand actually needs.
const picked = computed(() => vf.nodes.value.filter((n) => n.selected))
const ALIGN = [['left', 'alignLeft'], ['center-h', 'alignCenterH'], ['right', 'alignRight'],
               ['top', 'alignTop'], ['center-v', 'alignCenterV'], ['bottom', 'alignBottom']]
// Equal gaps only means something with three or more cards, so the button is not offered
// at two rather than sitting there disabled.
const aligns = computed(() => (picked.value.length >= 3 ? [...ALIGN, ['distribute-h', 'distributeH']] : ALIGN))

function align(how) {
  const box = picked.value.map((n) => ({
    id: n.id, x: n.computedPosition.x, y: n.computedPosition.y,
    w: n.dimensions.width, h: n.dimensions.height,
  }))
  if (box.length < 2) return
  const L = Math.min(...box.map((b) => b.x))
  const R = Math.max(...box.map((b) => b.x + b.w))
  const T = Math.min(...box.map((b) => b.y))
  const B = Math.max(...box.map((b) => b.y + b.h))
  const put = (id, x, y) => {
    const m = nodes.value.find((n) => n.id === id)
    if (m) m.position = { x: Math.round(x), y: Math.round(y) }
  }
  if (how === 'distribute-h') {
    // Ends stay put; the gaps between become equal. Widths differ per template, so the
    // free space is measured after subtracting every card's own width.
    const s = [...box].sort((a, b) => a.x - b.x)
    const gap = (s.at(-1).x + s.at(-1).w - s[0].x - s.reduce((a, b) => a + b.w, 0)) / (s.length - 1)
    let x = s[0].x
    for (const b of s) { put(b.id, x, b.y); x += b.w + gap }
  } else {
    for (const b of box) {
      const x = how === 'left' ? L : how === 'right' ? R - b.w : how === 'center-h' ? (L + R) / 2 - b.w / 2 : b.x
      const y = how === 'top' ? T : how === 'bottom' ? B - b.h : how === 'center-v' ? (T + B) / 2 - b.h / 2 : b.y
      put(b.id, x, y)
    }
  }
  dirty.value = true
}

const ICON = {
  left: '<path d="M1.6 1.8v12.4"/><rect x="4.2" y="3.6" width="9.4" height="3.4" rx=".8"/><rect x="4.2" y="9" width="6.2" height="3.4" rx=".8"/>',
  'center-h': '<path d="M8 1.4v13.2"/><rect x="3.4" y="3.6" width="9.2" height="3.4" rx=".8"/><rect x="5.6" y="9" width="4.8" height="3.4" rx=".8"/>',
  right: '<path d="M14.4 1.8v12.4"/><rect x="2.4" y="3.6" width="9.4" height="3.4" rx=".8"/><rect x="5.6" y="9" width="6.2" height="3.4" rx=".8"/>',
  top: '<path d="M1.8 1.6h12.4"/><rect x="3.6" y="4.2" width="3.4" height="9.4" rx=".8"/><rect x="9" y="4.2" width="3.4" height="6.2" rx=".8"/>',
  'center-v': '<path d="M1.4 8h13.2"/><rect x="3.6" y="3.4" width="3.4" height="9.2" rx=".8"/><rect x="9" y="5.6" width="3.4" height="4.8" rx=".8"/>',
  bottom: '<path d="M1.8 14.4h12.4"/><rect x="3.6" y="2.4" width="3.4" height="9.4" rx=".8"/><rect x="9" y="5.6" width="3.4" height="6.2" rx=".8"/>',
  'distribute-h': '<rect x="1.4" y="4" width="3.6" height="8" rx=".8"/><rect x="6.2" y="4" width="3.6" height="8" rx=".8"/><rect x="11" y="4" width="3.6" height="8" rx=".8"/><path d="M5.2 8h.8M10 8h.8"/>',
}

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
// The socket id of the condition ports. A wire between two of these carries no picture.
const CTL = '@ctl'

function canConnect(c) {
  if (!c.source || !c.target || c.source === c.target) return false
  const s = nodes.value.find((n) => n.id === c.source)
  const d = nodes.value.find((n) => n.id === c.target)
  if (!s || !d) return false
  const fromCtl = c.sourceHandle === CTL, toCtl = c.targetHandle === CTL
  // Either both ends are condition sockets or neither is: one carries "that step ended
  // this way", the other carries a file, and a wire cannot do both.
  if (fromCtl !== toCtl) return false
  if (fromCtl) {
    return !edges.value.some((e) => e.id !== c.id && e.source === c.source && e.target === c.target
                              && e.data.kind === 'control')
  }
  const port = d.data.tpl.ports.in.find((p) => p.name === c.targetHandle)
  if (!port || port.type !== s.data.tpl.media) return false
  return !edges.value.some((e) => e.id !== c.id && e.target === c.target && e.targetHandle === c.targetHandle)
}

function onConnect(c) {
  if (!canConnect(c)) return
  const e = c.sourceHandle === CTL ? mkCtl(c.source, c.target)
    : mkEdge(c.source, c.sourceHandle, c.target, c.targetHandle, 0)
  edges.value = [...edges.value, e]
  dirty.value = true
}

// The wire's own tag: which result of which repetition. Language-neutral because it is
// drawn on the wire, where a translated word would not fit.
function edgeLabel(attempt, index) {
  return `${attempt ? `r${attempt + 1}·` : ''}#${index + 1}`
}

function mkCtl(source, target, when = 'fail') {
  return {
    id: `e-${source}-ctl-${target}`,
    source, target, sourceHandle: CTL, targetHandle: CTL,
    type: 'smoothstep', class: 'ctl',
    data: { kind: 'control', when },
    label: when,
    labelBgPadding: [4, 2], labelBorderRadius: 0,
    style: { stroke: '#d9a13b', strokeWidth: 1.4, strokeDasharray: '5 4' },
    markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: '#d9a13b' },
  }
}

function mkEdge(source, sourceHandle, target, targetHandle, index, attempt = 0) {
  return {
    id: `e-${source}-${sourceHandle}-${target}-${targetHandle}`,
    source, target, sourceHandle, targetHandle,
    type: 'smoothstep',
    data: { index, attempt },
    label: edgeLabel(attempt, index),
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
    e.label = edgeLabel(e.data.attempt ?? 0, e.data.index)
    dirty.value = true
  },
})
// How many repetitions the upstream step was told to make -- the ceiling for 第几遍.
const pickedRepMax = computed(() => pickedSource.value?.data?.repeat || 1)
const pickedAttempt = computed({
  get: () => (pickedEdge.value?.data.attempt ?? 0) + 1,
  set: (v) => {
    const e = pickedEdge.value
    if (!e) return
    e.data.attempt = Math.min(Math.max(0, Math.round(v) - 1), pickedRepMax.value - 1)
    e.label = edgeLabel(e.data.attempt, e.data.index ?? 0)
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
// A condition wire names no file, so the panel shows the condition instead of a picture.
const whenOptions = computed(() => [
  { value: 'fail', label: t.value.whenFail },
  { value: 'ok', label: t.value.whenOk },
  { value: 'always', label: t.value.whenAlways }])

function setWhen(v) {
  const e = pickedEdge.value
  if (!e) return
  e.data.when = v
  e.label = v
  dirty.value = true
}

const pickedName = computed(() => {
  if (pickedEdge.value?.data.kind === 'control') return ''
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
    const out = edges.value.filter((e) => e.source === n.id && e.data.kind !== 'control')
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
  nodes.value.map((n) => `${n.id}|${JSON.stringify(n.data.params)}|${n.data.repeat}|${n.data.retries}`
    + `|${n.data.on_error}|${n.data.gate}`).join('#'),
  edges.value.map((e) => `${e.source}>${e.target}:${e.targetHandle}:${e.data.kind === 'control'
    ? e.data.when : `${e.data.index}:${e.data.attempt ?? 0}`}`).join('#'),
].join('||'))
watch(authored, decorate)

function toGraph() {
  return {
    nodes: nodes.value.map((n) => ({
      id: n.id, template: n.data.tpl.id, params: n.data.params,
      // Only a step that deviates from "no retry, stop the chain" says so: an untouched
      // canvas keeps the shape it was authored with.
      ...(n.data.retries ? { retries: n.data.retries } : {}),
      ...(n.data.on_error && n.data.on_error !== 'stop' ? { on_error: n.data.on_error } : {}),
      ...(n.data.repeat > 1 ? { repeat: n.data.repeat } : {}),
      ...(n.data.gate && n.data.gate !== 'off' ? { gate: n.data.gate } : {}),
      position: { x: Math.round(n.position.x), y: Math.round(n.position.y) },
    })),
    edges: edges.value.map((e) => e.data.kind === 'control'
      ? { from: e.source, to: e.target, kind: 'control', when: e.data.when }
      : ({
        from: e.source, out: e.sourceHandle, to: e.target, in: e.targetHandle, index: e.data.index ?? 0,
        ...(e.data.attempt ? { attempt: e.data.attempt } : {}),
      })),
  }
}

function fromGraph(g, tplById) {
  nodes.value = (g.nodes || []).map((n) => {
    const tpl = tplById[n.template]
    return { id: n.id, type: 'step', position: { ...n.position },
             data: { tpl, params: { ...clone(tpl.defaults), ...n.params }, order: 0, run: null,
                     changed: [], pickIdx: 0, retries: n.retries || 0, on_error: n.on_error || 'stop',
                     repeat: n.repeat || 1, gate: n.gate || 'off' } }
  })
  edges.value = (g.edges || []).map((e) => e.kind === 'control' ? mkCtl(e.from, e.to, e.when)
    : mkEdge(e.from, e.out, e.to, e.in, e.index ?? 0, e.attempt ?? 0))
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
  refit()
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
  if (['done', 'error', 'cancelled', 'partial'].includes(st.state)) stop()
}

// Cancelling is a request, not a stop: the worker sees it between its polls, so the bar
// says 正在取消 until the run row itself changes.
async function cancel() {
  if (!run.value?.run) return
  try {
    await api.cancelFlowRun(run.value.run)
    err.value = ''
    await poll()   // the reply is only the flag; the steps still come from the run row
  } catch (e) {
    err.value = e.message
  }
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

// The stage changes size when the window does, and a fitted chain stops being fitted at
// the new width: at 1600 two of three cards were in view until something else reframed.
// Debounced because a drag-resize fires per frame, and the first callback is the observe.
let ro = null, roTimer = null, roW = 0
onMounted(() => {
  roW = stageEl.value?.getBoundingClientRect().width || 0
  ro = new ResizeObserver(([e]) => {
    const w = e.contentRect.width
    if (Math.abs(w - roW) < 24) return
    roW = w
    clearTimeout(roTimer)
    roTimer = setTimeout(reframe, 250)
  })
  if (stageEl.value) ro.observe(stageEl.value)
})
onBeforeUnmount(() => { stop(); ro?.disconnect(); clearTimeout(roTimer) })
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
      <button class="ghost" :disabled="!running" :title="t.canvasCancelHint" @click="cancel">
        ■ {{ t.canvasCancel }}
      </button>
      <span v-if="run" class="rstate" :class="run.state">
        <i class="dot" />{{ t.canvasState[run.state] }}
        <b v-if="run.error" class="rerr">{{ run.error }}</b>
      </span>
    </div>
    <p v-if="err" class="drift">{{ err }}</p>

    <div class="flowpage">
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

      <div class="stage" :class="{ fitting }" ref="stageEl">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :is-valid-connection="canConnect"
          :delete-key-code="null"
          :selection-mode="SelectionMode.Partial"
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

          <Panel position="bottom-left" class="toolbar">
            <span class="zoomer">
              <button class="zb" :title="t.canvasZoomIn" @click="zoomIn()">＋</button>
              <button class="zb" :title="t.canvasZoomOut" @click="zoomOut()">－</button>
              <button class="zb" :title="t.canvasFit" @click="reframe()">▣</button>
            </span>
            <!-- One strip, left-aligned: bottom-centre put the last button under the
                 parameter overlay whenever both were open. -->
            <template v-if="picked.length >= 2">
              <i class="tdiv" />
              <span class="alabel" :title="t.alignHow">{{ t.alignTitle }} {{ picked.length }}</span>
              <button v-for="[how, key] in aligns" :key="how" class="ab" :title="t[key]" @click="align(how)">
                <svg viewBox="0 0 16 16" aria-hidden="true" v-html="ICON[how]" />
              </button>
            </template>
          </Panel>

          <Panel v-if="pickedEdge" position="top-center" class="wire">
            <span class="wt">{{ edgeEnds }}</span>
            <label v-if="pickedEdge.data.kind === 'control'" class="wl">{{ t.canvasWhen }}
              <Select :model-value="pickedEdge.data.when" :options="whenOptions" :label="t.canvasWhen"
                      @update:model-value="setWhen($event)" />
            </label>
            <template v-else>
              <label class="wl">{{ t.canvasFrame }}
                <NumberField v-model="pickedFrame" :min="1" :max="pickedMax" :label="t.canvasFrame" />
              </label>
              <label v-if="pickedRepMax > 1" class="wl">{{ t.canvasAttempt }}
                <NumberField v-model="pickedAttempt" :min="1" :max="pickedRepMax" :label="t.canvasAttempt" />
              </label>
            </template>
            <span v-if="pickedName" class="wf">{{ pickedName }}</span>
            <button class="ghost sm" @click="delEdge(pickedEdge.id)">{{ t.canvasDelWire }}</button>
            <button class="ghost sm" :title="t.close" @click="selEdge = null">✕</button>
          </Panel>
        </VueFlow>
        <p v-if="!nodes.length" class="hint0">{{ t.canvasEmptyHint }}</p>

        <ParamPanel v-if="editingNode" :template="editingNode.data.tpl" :params="editingNode.data.params"
                    :models="models?.catalog" :err="err" :show-run="false" :policy="editingNode.data"
                    @close="editing = null" @del="editing && delNode(editing)" @policy="dirty = true" />
      </div>
    </div>

    <Lightbox v-if="zoom" :title="t.variants" :code="''" :files="zoom.files" :index="zoom.index"
              @close="zoom = null" @update:index="zoom.index = $event" />
  </div>
</template>
