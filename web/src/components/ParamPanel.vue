<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from '../i18n'
import { api } from '../api'
import Select from './Select.vue'
import NumberField from './NumberField.vue'
import FileField from './FileField.vue'

const props = defineProps({ template: Object, params: Object, models: Object, refShot: Object,
                           routes: Array, busy: Boolean, err: String,
                           // The card's own cover, handed over so the header shows the same
                           // picture the row shows rather than a second choice of its own.
                           coverShot: String,
                           // The chain step's own failure policy, when this panel is editing a
                           // step on the canvas rather than a single run from the list.
                           policy: Object,
                           // The canvas uses this panel as a plain parameter form: ▶ 生成
                           // there would start one step of a chain nobody asked to run alone.
                           showRun: { type: Boolean, default: true } })
const emit = defineEmits(['submit', 'close', 'route', 'del', 'meta', 'policy'])
const { t } = useI18n()

const tab = ref('basic')

// A chain step is allowed to fail without taking the chain down with it; the ceiling is
// the server's MAX_RETRY, and it is a ceiling because one attempt is a whole generation.
const retryOptions = [0, 1, 2, 3].map((n) => ({ value: n, label: String(n) }))
const repeatOptions = [1, 2, 3, 4, 6, 8].map((n) => ({ value: n, label: String(n) }))
const onErrorOptions = computed(() => [
  { value: 'stop', label: t.value.canvasStop }, { value: 'skip', label: t.value.canvasSkip }])

// Say what the settings cost before anyone presses run: repetitions times attempts,
// against the template's own per-run budget.
const worstCase = computed(() => {
  const rep = props.policy?.repeat ?? 1
  const tries = 1 + (props.policy?.retries ?? 0)
  const mins = Math.round((props.template?.timeout || 900) / 60)
  return t.value.canvasWorst.replace(/\{(\w+)\}/g, (_, k) => ({ rep, tries, n: rep * tries, mins })[k])
})

function setPolicy(key, value) {
  if (!props.policy) return
  props.policy[key] = value
  emit('policy')
}

// ---------------------------------------------------------------- the workflow file
// The same graph POST /tasks submits, as the two files ComfyUI knows. Fetched lazily:
// nobody who never opens the tab should pay a request per keystroke.
const wf = ref(null), wfErr = ref(''), wfBusy = ref(false), copied = ref(false)
const fmt = ref('ui')
let timer = null

function load() {
  if (!props.showRun || tab.value !== 'json' || !props.template) return
  clearTimeout(timer)
  wfBusy.value = true
  timer = setTimeout(async () => {
    try {
      wf.value = await api.exportWorkflow({ template: props.template.id, params: props.params, format: fmt.value })
      wfErr.value = ''
    } catch (e) {
      wfErr.value = e.message
    } finally {
      wfBusy.value = false
    }
  }, 350)
}

const pretty = computed(() => (wf.value ? JSON.stringify(wf.value.workflow, null, 2) : ''))
// A data: URL rather than a generated blob: the Save-As dialog gets the filename the server
// chose, and there is no object URL left behind to revoke at the right moment.
const href = computed(() => 'data:application/json;charset=utf-8,' + encodeURIComponent(pretty.value))
function save() {
  const a = document.createElement('a')
  a.href = href.value
  a.download = wf.value.filename
  a.click()
}
const stats = computed(() => {
  if (!wf.value) return t.value.jsonLoading
  const s = [`${wf.value.nodes} ${t.value.jsonNodes}`, `${wf.value.links} ${t.value.jsonLinks}`]
  if (wf.value.defs_from) {
    s.push(wf.value.defs_from === 'engine' ? t.value.jsonFromEngine : t.value.jsonFromCache)
  }
  return s.join(' · ')
})

async function copy() {
  try {
    await navigator.clipboard.writeText(pretty.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1600)
  } catch {
    wfErr.value = `${t.value.jsonFail}: clipboard`
  }
}

// ------------------------------------------------------------- one click into ComfyUI
// The engine tab is a different origin, so this page cannot load a graph into it. It writes
// the file into ComfyUI's own workflows dir instead and asks the tab's loader extension to
// open that path; the extension acks back, which is the only proof we get that it worked.
const comfy = ref(''), comfyMsg = ref('')
let waiting = null, pings = null

function heard(e) {
  const d = e.data || {}
  if ((d.type !== 'studio:loaded' && d.type !== 'studio:failed') || d.path !== waiting) return
  clearInterval(pings)
  pings = null
  comfy.value = d.type === 'studio:loaded' ? 'ok' : 'fail'
  comfyMsg.value = d.type === 'studio:loaded' ? `${d.nodes} ${t.value.jsonNodes}` : (d.error || '')
  if (comfy.value === 'ok') setTimeout(() => { comfy.value = '' }, 4000)
}
window.addEventListener('message', heard)
onBeforeUnmount(() => {
  window.removeEventListener('message', heard)
  clearInterval(pings)
})

async function openInComfy() {
  comfy.value = 'busy'
  comfyMsg.value = ''
  let r
  try {
    r = await api.pushWorkflow({ template: props.template.id, params: props.params })
  } catch (e) {
    comfy.value = 'fail'
    comfyMsg.value = e.message
    return
  }
  waiting = r.path
  const origin = new URL(r.comfy_url).origin
  const win = window.open(r.comfy_url, 'comfyui-studio')
  // A tab that was not open yet has no listener when we first post, so keep posting until it
  // answers. The extension reloads the same file on a duplicate post, which costs nothing.
  let tries = 0
  clearInterval(pings)
  pings = setInterval(() => {
    if (!win || win.closed) { clearInterval(pings); pings = null; comfy.value = 'fail'; comfyMsg.value = t.value.jsonOpenHint; return }
    if (comfy.value === 'ok') { clearInterval(pings); pings = null; return }
    if (++tries > 25) {
      clearInterval(pings)
      pings = null
      comfy.value = 'fail'
      comfyMsg.value = t.value.jsonOpenHint
      return
    }
    win.postMessage({ type: 'studio:load', path: r.path }, origin)
  }, 400)
}

// ------------------------------------------------------- the row's own label and cover
// Name, note and cover are stored on the server against the template id; the registry's own
// copy stays underneath them, so clearing a field falls back to it rather than to blank.
const meta = ref({ name: '', desc: '' })
const metaBusy = ref(false)
const metaMsg = ref(''), metaErr = ref('')
const coverEl = ref(null)
// The header tile falls back to the mark when the cover it was given cannot be shown --
// the engine's output directory is one the result track can empty.
const icoBroken = ref(false)
watch(() => props.coverShot, () => { icoBroken.value = false })
// What the box is named after: the file chosen a moment ago, or the one the server says this
// row's cover is -- the stored upload, or the result picture the row fell back to.
const picked = ref('')
const coverBroken = ref(false)
const coverName = computed(() => picked.value || props.template?.cover_name || '')
watch(() => props.template?.cover, () => { coverBroken.value = false })

function fillMeta() {
  // The row already carries the effective text (override if there is one, registry copy
  // otherwise), so the boxes open with something editable in them rather than a grey hint
  // the person has to replace by hand.
  meta.value = { name: props.template?.name || '', desc: props.template?.desc || '' }
  picked.value = ''
  metaMsg.value = metaErr.value = ''
}

async function sendCover(file) {
  if (!file) return
  metaBusy.value = true
  metaErr.value = ''
  try {
    // A data: URL in the same JSON body every other call uses: multipart would cost a new
    // server dependency to move one small picture.
    await api.setCover(props.template.id, { filename: file.name, image: await dataUrl(file) })
    picked.value = file.name    // the bytes land under the row's own id; the name they came in with stays
    metaMsg.value = t.value.metaCoverSet
    emit('meta')
  } catch (e) {
    metaErr.value = e.message
  } finally {
    metaBusy.value = false
  }
}

function dataUrl(file) {
  return new Promise((ok, no) => {
    const r = new FileReader()
    r.onload = () => ok(r.result)
    r.onerror = () => no(new Error(t.value.readFail))
    r.readAsDataURL(file)
  })
}

function onCoverPick(e) {
  sendCover(e.target.files?.[0])
  e.target.value = ''      // so choosing the same file twice still fires a change
}

function onCoverDrop(e) {
  sendCover(e.dataTransfer?.files?.[0])
}

async function saveMeta() {
  metaBusy.value = true
  try {
    await api.workflowMeta(props.template.id, meta.value)
    metaMsg.value = t.value.metaSaved
    metaErr.value = ''
    emit('meta')
  } catch (e) {
    metaErr.value = e.message
  } finally {
    metaBusy.value = false
  }
}

async function dropCover() {
  metaBusy.value = true
  try {
    await api.clearCover(props.template.id)
    picked.value = ''
    metaMsg.value = t.value.metaCoverCleared
    metaErr.value = ''
    emit('meta')
  } catch (e) {
    metaErr.value = e.message
  } finally {
    metaBusy.value = false
  }
}

watch(tab, (v) => { if (v === 'json' && !wf.value) load(); if (v === 'meta') fillMeta() })
watch(() => props.template?.id, () => { wf.value = null; load(); if (tab.value === 'meta') fillMeta() })
watch(fmt, () => { wf.value = null; load() })
watch(() => props.params, load, { deep: true })
onBeforeUnmount(() => clearTimeout(timer))
// The template's own resolution is always offered: a video graph runs at 832x480,
// which is not a picture size anyone would pick for an icon, and omitting it left
// the select with no matching option -- rendered blank and silently unchangeable.
const SIZES = computed(() => {
  const base = [[512, 512], [768, 768], [1024, 1024], [1024, 768], [768, 1024]]
  const d = props.template?.defaults
  const own = d?.width && d?.height ? [[d.width, d.height]] : []
  // A template whose model has its own size grid (Qwen-Image 2.1 ships 2K natively)
  // declares it; offering 512x512 next to a 2K-native backbone is a trap, not a choice.
  const grid = props.template?.sizes?.length ? props.template.sizes : base
  const seen = new Set()
  return [...own, ...grid].filter(([w, h]) => !seen.has(`${w}x${h}`) && seen.add(`${w}x${h}`))
})
const sizeKey = computed({
  get: () => `${props.params.width}x${props.params.height}`,
  set: (v) => {
    const [w, h] = v.split('x').map(Number)
    props.params.width = w
    props.params.height = h
  },
})
const sizeOptions = computed(() => SIZES.value.map(([w, h]) => ({ value: `${w}x${h}`, label: `${w} × ${h}` })))

// The dropdown is the engine's own list. "已量" here means this exact weight is the
// pairing the icon numbers were measured on -- deliberately different wording from
// a template's 已验证, which claims the graph ran, not that this weight is the one
// behind the published figures.
const unets = computed(() => props.models?.unet || [])
function badge(name) {
  return unets.value.find((u) => u.name === name)?.verified ? t.value.pairMeasured : t.value.pairUnmeasured
}
function tip(name) {
  return unets.value.find((u) => u.name === name)?.verified ? t.value.verifiedTip : t.value.unverifiedTip
}
const unetOptions = computed(() => unets.value.map((u) => ({
  value: u.name, label: `${u.name.replace('.safetensors', '')} · ${badge(u.name)}`, hint: tip(u.name),
})))

// The 4x weights are the engine's own list too, for the same reason as the unets.
const upscaleOptions = computed(() => (props.models?.upscale || []).map((u) => ({
  value: u.name, label: `${u.name} · ${u.verified ? t.value.pairMeasured : t.value.pairUnmeasured}`,
})))

const has = (f) => props.template?.fields.includes(f)

// The two sampling names come from the engine's own KSampler combo. A run stored before
// this list changed can carry a name the engine no longer offers, and a select with no
// matching option renders blank -- which reads as "nothing chosen", not "this is gone",
// so the odd value is kept and labelled instead of dropped.
function named(list, cur) {
  const seen = new Set(list || [])
  const opts = [...seen].map((v) => ({ value: v, label: v }))
  if (cur && !seen.has(cur)) opts.push({ value: cur, label: cur, hint: t.value.notInEngine })
  return opts
}
const samplerOptions = computed(() => named(props.models?.samplers, props.params.sampler))
const schedulerOptions = computed(() => named(props.models?.schedulers, props.params.scheduler))

// Fields with no dedicated control get a plain input, inferred numeric or text from
// the template's own default. New graph knobs then appear without editing this file.
const DEDICATED = ['prompt', 'negative', 'width', 'height', 'batch', 'steps', 'cfg', 'seed', 'unet', 'clip',
                   'shift', 'sampler', 'scheduler', 'denoise', 'image', 'video', 'model',
                   'ref1', 'ref2', 'ref3', 'ref4']
const extras = computed(() => (props.template?.fields || []).filter((f) => !DEDICATED.includes(f)))
// Reference slots are filenames the engine must be able to read, so they get the same
// upload-or-drop control as `image` -- a text box here invites a path that is not there.
const refFields = computed(() => (props.template?.fields || []).filter((f) => f.startsWith('ref') && f !== 'ref_size'))
function isNum(f) { return typeof props.template?.defaults?.[f] === 'number' }
function labelFor(f) { return t.value[f] || t.value.th[f] || f }

// Enum knobs whose values belong to the engine, not to us. A text box where only
// "match" and "max" are valid is a control that is wrong two thirds of the time.
const ENGINE_COMBO = { ref_size: 'refsizing' }
function comboOptions(f) {
  const list = props.models?.[ENGINE_COMBO[f]]
  return list?.length ? named(list, props.params[f]) : null
}

// 2000 is POST /tasks' own ceiling on the prompt, so the counter can say where the
// request will start being refused instead of discovering it after the click.
const MAXPROMPT = 2000
const needPrompt = ref(false)
const goLabel = computed(() => ({ video: t.value.generateVideo, model: t.value.generateModel }[props.template?.media]
  || t.value.generate))

function go() {
  // Only prompt-taking templates are checked; the 3D chain is driven by an image.
  needPrompt.value = has('prompt') && !props.params.prompt?.trim()
  if (needPrompt.value) return
  emit('submit')
}
</script>

<template>
  <aside class="drawer">
    <header class="dhead">
      <span class="dico">
        <img v-if="coverShot && !icoBroken" :src="coverShot" :alt="template.name" @error="icoBroken = true" />
        <template v-else>◈</template>
      </span>
      <h2 class="dname">{{ template.name }}<span class="chip">{{ template.model }}</span></h2>
      <button class="icon ghost" :title="t.close" @click="emit('close')">✕</button>
      <p class="ddesc">{{ template.desc }}</p>
    </header>

    <div class="dtabs">
      <button class="ghost sm" :class="{ on: tab === 'basic' }" @click="tab = 'basic'">{{ t.drawerParams }}</button>
      <button class="ghost sm" :class="{ on: tab === 'adv' }" @click="tab = 'adv'">{{ t.drawerAdvanced }}</button>
      <button v-if="!showRun" class="ghost sm" :class="{ on: tab === 'step' }" @click="tab = 'step'">
        {{ t.drawerStep }}
      </button>
      <button v-if="showRun" class="ghost sm" :disabled="comfy === 'busy'" @click="openInComfy">
        {{ comfy === 'busy' ? t.jsonOpening : comfy === 'ok' ? t.jsonOpened : t.jsonOpen }}
      </button>
      <button v-if="showRun" class="ghost sm" :class="{ on: tab === 'json' }" @click="tab = 'json'">
        {{ t.drawerJson }}
      </button>
      <button v-if="showRun" class="ghost sm" :class="{ on: tab === 'meta' }" @click="tab = 'meta'">
        {{ t.drawerMeta }}
      </button>
    </div>
    <p v-if="comfy === 'ok' || comfy === 'fail'" class="jmeta dstatus" :class="{ warn: comfy === 'fail' }">
      {{ comfy === 'ok' ? `${t.jsonOpened} · ${comfyMsg}` : `${t.jsonOpenFail}${comfyMsg}` }}
    </p>

    <div class="dbody">
      <p v-if="err" class="drift">{{ err }}</p>

      <template v-if="tab === 'basic'">
        <label v-if="routes?.length > 1" class="ff-row">{{ t.route }}
          <Select :model-value="template.id" :options="routes.map(r => ({ value: r.id, label: r.name }))"
                  :label="t.route" @update:model-value="emit('route', $event)" />
        </label>

        <label v-if="has('unet')">{{ t.model }}
          <Select v-model="params.unet" :options="unetOptions" :label="t.model" />
        </label>

        <label v-if="has('model')">{{ t.upscaleModel }}
          <Select v-model="params.model" :options="upscaleOptions" :label="t.upscaleModel" />
        </label>

        <label v-if="has('prompt')" class="counted">{{ t.prompt }}
          <textarea v-model="params.prompt" rows="3" />
          <small class="count" :class="{ over: (params.prompt?.length || 0) > MAXPROMPT }">
            {{ params.prompt?.length || 0 }} / {{ MAXPROMPT }}
          </small>
        </label>
        <label v-if="has('negative')" class="counted">{{ t.negative }}
          <textarea v-model="params.negative" rows="3" />
          <small class="count" :class="{ over: (params.negative?.length || 0) > MAXPROMPT }">
            {{ params.negative?.length || 0 }} / {{ MAXPROMPT }}
          </small>
        </label>

        <div v-if="refShot && !params.image && !params.video" class="refrow">
          <video v-if="/\.(mp4|webm|mov)$/i.test(refShot.filename || '')" :src="refShot.url" preload="metadata" muted />
          <img v-else :src="refShot.url" :alt="refShot.filename" />
          <span>{{ t.refImage }} · {{ t.refFrom }} {{ refShot.from }}<br />
            <small>{{ t.useForVideoHint }}</small></span>
        </div>

        <label v-if="has('image')" class="ff-row">{{ t.image }}
          <FileField v-model="params.image" :label="t.image" />
        </label>

        <label v-if="has('video')" class="ff-row">{{ t.video }}
          <FileField v-model="params.video" :label="t.video" kind="video" />
        </label>

        <label v-for="f in refFields" :key="f" class="ff-row">{{ labelFor(f) }}
          <FileField v-model="params[f]" :label="labelFor(f)" />
        </label>

        <div v-if="extras.length" class="grp">
          <label v-for="f in extras" :key="f">{{ labelFor(f) }}
            <Select v-if="comboOptions(f)" v-model="params[f]" :options="comboOptions(f)" :label="labelFor(f)" />
            <NumberField v-else-if="isNum(f)" v-model="params[f]" :label="labelFor(f)" />
            <input v-else v-model="params[f]" />
          </label>
        </div>

        <div class="grp">
          <label v-if="has('width')" class="grow">{{ t.size }}
            <Select v-model="sizeKey" :options="sizeOptions" :label="t.size" />
          </label>
          <label v-if="has('batch')" class="num-field">{{ t.batchN }}
            <NumberField v-model="params.batch" :min="1" :max="4" :label="t.batchN" />
          </label>
        </div>

        <div class="slider" v-if="has('steps')">
          <span>{{ t.steps }}</span>
          <input v-model.number="params.steps" type="range" min="1" max="50" />
          <NumberField class="box" v-model="params.steps" :min="1" :max="50" :label="t.steps" />
        </div>
        <div class="slider" v-if="has('cfg')">
          <span>{{ t.cfg }}</span>
          <input v-model.number="params.cfg" type="range" min="0.5" max="10" step="0.1" />
          <NumberField class="box" v-model="params.cfg" :min="0.5" :max="10" :step="0.1" :label="t.cfg" />
        </div>

        <label v-if="has('seed')">{{ t.seed }}
          <span class="seedctl">
            <NumberField v-model="params.seed" :min="-1" :label="t.seed" />
            <button class="ghost seedroll" :title="t.randomSeed" :aria-label="t.randomSeed"
                    @click="params.seed = Math.floor(Math.random() * 1e9)">↻</button>
          </span>
        </label>
      </template>

      <div v-else-if="tab === 'meta'" class="metawrap">
        <label>{{ t.metaName }}
          <input v-model="meta.name" :maxlength="60" />
        </label>
        <label class="counted">{{ t.metaDesc }}
          <textarea v-model="meta.desc" rows="3" :maxlength="400" />
          <small class="count">{{ meta.desc.length }} / 400</small>
        </label>

        <!-- 封面 is a field label like the two above it, not a section heading: the picker sits
             under the word the same way the name box sits under 名称. -->
        <label class="coverfield">{{ t.metaCover }}
          <span class="ff" :class="{ busy: metaBusy }">
            <button type="button" class="ghost ff-pick" :disabled="metaBusy" :title="coverName || t.metaCoverPick"
                    @click="coverEl?.click()" @dragover.prevent @drop.prevent="onCoverDrop">
              <span class="ff-name">{{ metaBusy ? t.uploading : (coverName || t.metaCoverChoose) }}</span>
              <span class="ff-hint">{{ t.dropHere }}</span>
            </button>
            <span class="ff-prev cover-prev">
              <img v-if="template.cover && !coverBroken" :src="template.cover" :alt="t.metaCover"
                   @error="coverBroken = true" />
              <span v-else class="ff-glyph">＋</span>
            </span>
            <input ref="coverEl" class="ff-input" type="file" accept="image/*"
                   :aria-label="t.metaCover" @change="onCoverPick" />
          </span>
        </label>
        <button v-if="template.cover_pinned" class="ghost sm cover-clear" :disabled="metaBusy" @click="dropCover">
          {{ t.metaCoverClear }}
        </button>
        <p v-if="metaMsg" class="jmeta">{{ metaMsg }}</p>
        <p v-if="metaErr" class="drift">{{ metaErr }}</p>
        <button class="go" :disabled="metaBusy" @click="saveMeta">{{ t.metaSave }}</button>
      </div>

      <div v-else-if="tab === 'json'" class="jsonwrap">
        <div class="jbar">
          <button class="ghost sm" :class="{ on: fmt === 'ui' }" @click="fmt = 'ui'">{{ t.jsonUi }}</button>
          <button class="ghost sm" :class="{ on: fmt === 'api' }" @click="fmt = 'api'">{{ t.jsonApi }}</button>
          <span class="jgrow"></span>
          <button class="ghost sm" :disabled="!pretty" @click="copy">
            {{ copied ? t.jsonCopied : t.jsonCopy }}
          </button>
          <button class="ghost sm" :disabled="!pretty" @click="save">{{ t.download }}</button>
        </div>
        <p class="jmeta">{{ stats }}<template v-if="wf"> · {{ wf.filename }}</template></p>
        <p v-if="wf?.unfilled?.length" class="drift">
          {{ t.jsonUnfilled }}{{ wf.unfilled.join('、') }} — {{ t.jsonUnfilledFix }}
        </p>
        <p v-if="wfErr" class="drift">{{ t.jsonFail }} {{ wfErr }}</p>
        <pre v-if="pretty" class="jsonbox">{{ pretty }}</pre>
      </div>

      <div v-else-if="tab === 'adv'" class="adv">
        <label class="inrow">{{ t.shift }}<NumberField v-model="params.shift" :step="0.5" :label="t.shift" /></label>
        <label class="inrow">{{ t.sampler }}<Select v-model="params.sampler" :options="samplerOptions" :label="t.sampler" /></label>
        <label class="inrow">{{ t.scheduler }}<Select v-model="params.scheduler" :options="schedulerOptions" :label="t.scheduler" /></label>
        <label class="inrow">{{ t.denoise }}<NumberField v-model="params.denoise" :step="0.05" :label="t.denoise" /></label>
        <p class="hint">高级参数只在模板声明了对应节点时才生效。</p>
      </div>

      <!-- Only a step of a chain has a next step to fail forward into, so this tab exists
           only where the panel is editing a canvas step. -->
      <div v-else-if="tab === 'step'" class="stepwrap">
        <label class="inrow">{{ t.canvasRepeat }}
          <Select :model-value="policy?.repeat ?? 1" :options="repeatOptions" :label="t.canvasRepeat"
                  @update:model-value="setPolicy('repeat', $event)" />
        </label>
        <label class="inrow">{{ t.canvasRetry }}
          <Select :model-value="policy?.retries ?? 0" :options="retryOptions" :label="t.canvasRetry"
                  @update:model-value="setPolicy('retries', $event)" />
        </label>
        <label class="inrow">{{ t.canvasOnErr }}
          <Select :model-value="policy?.on_error || 'stop'" :options="onErrorOptions" :label="t.canvasOnErr"
                  @update:model-value="setPolicy('on_error', $event)" />
        </label>
        <p class="jmeta">{{ worstCase }}</p>
        <p class="hint">{{ t.canvasRepeatHint }}</p>
        <p class="hint">{{ t.canvasRetryHint }}。{{ t.canvasOnErrHint }}。</p>
      </div>

      <p v-if="needPrompt" class="drift">{{ t.needPrompt }}</p>
      <!-- 设置 has its own action at the bottom of the tab; a second full-width button under
           it would be two things to press at the same spot. -->
      <button v-if="showRun && tab !== 'meta'" class="go" :disabled="busy" @click="go">
        ▶ {{ busy ? t.generating : goLabel }}
      </button>
      <button v-else-if="tab !== 'meta'" class="ghost delstep" @click="emit('del')">{{ t.canvasDelStep }}</button>
    </div>
  </aside>
</template>
