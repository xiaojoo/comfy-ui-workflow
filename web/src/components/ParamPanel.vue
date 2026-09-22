<script setup>
import { computed, ref } from 'vue'
import { useI18n } from '../i18n'
import Select from './Select.vue'
import NumberField from './NumberField.vue'
import FileField from './FileField.vue'

const props = defineProps({ template: Object, params: Object, models: Object, refShot: Object,
                           routes: Array, busy: Boolean, err: String,
                           // The canvas uses this panel as a plain parameter form: ▶ 生成
                           // there would start one step of a chain nobody asked to run alone.
                           showRun: { type: Boolean, default: true } })
const emit = defineEmits(['submit', 'close', 'route', 'del'])
const { t } = useI18n()

const tab = ref('basic')
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
      <span class="dico">◈</span>
      <div class="dtitle">
        <h2>{{ template.name }}<span class="chip">{{ template.model }}</span></h2>
        <p>{{ template.desc }}</p>
      </div>
      <button class="icon ghost" :title="t.close" @click="emit('close')">✕</button>
    </header>

    <div class="dtabs">
      <button class="ghost sm" :class="{ on: tab === 'basic' }" @click="tab = 'basic'">{{ t.drawerParams }}</button>
      <button class="ghost sm" :class="{ on: tab === 'adv' }" @click="tab = 'adv'">{{ t.drawerAdvanced }}</button>
    </div>

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

      <div v-else class="adv">
        <label class="inrow">{{ t.shift }}<NumberField v-model="params.shift" :step="0.5" :label="t.shift" /></label>
        <label class="inrow">{{ t.sampler }}<Select v-model="params.sampler" :options="samplerOptions" :label="t.sampler" /></label>
        <label class="inrow">{{ t.scheduler }}<Select v-model="params.scheduler" :options="schedulerOptions" :label="t.scheduler" /></label>
        <label class="inrow">{{ t.denoise }}<NumberField v-model="params.denoise" :step="0.05" :label="t.denoise" /></label>
        <p class="hint">高级参数只在模板声明了对应节点时才生效。</p>
      </div>

      <p v-if="needPrompt" class="drift">{{ t.needPrompt }}</p>
      <button v-if="showRun" class="go" :disabled="busy" @click="go">▶ {{ busy ? t.generating : goLabel }}</button>
      <button v-else class="ghost delstep" @click="emit('del')">{{ t.canvasDelStep }}</button>
    </div>
  </aside>
</template>
