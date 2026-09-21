<script setup>
import { computed, ref } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({ template: Object, params: Object, models: Object, busy: Boolean })
const emit = defineEmits(['submit'])
const { t } = useI18n()

const adv = ref(false)
// The template's own resolution is always offered: a video graph runs at 832x480,
// which is not a picture size anyone would pick for an icon, and omitting it left
// the select with no matching option -- rendered blank and silently unchangeable.
const SIZES = computed(() => {
  const base = [[512, 512], [768, 768], [1024, 1024], [1024, 768], [768, 1024]]
  const d = props.template?.defaults
  const own = d?.width && d?.height ? [[d.width, d.height]] : []
  const seen = new Set()
  return [...own, ...base].filter(([w, h]) => !seen.has(`${w}x${h}`) && seen.add(`${w}x${h}`))
})
const sizeKey = computed(() => `${props.params.width}x${props.params.height}`)

function pickSize(v) {
  const [w, h] = v.split('x').map(Number)
  props.params.width = w
  props.params.height = h
}

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

const has = (f) => props.template?.fields.includes(f)

// Fields with no dedicated control get a plain input, inferred numeric or text from
// the template's own default. New graph knobs then appear without editing this file.
const DEDICATED = ['prompt', 'negative', 'width', 'height', 'batch', 'steps', 'cfg', 'seed', 'unet', 'clip',
                   'shift', 'sampler', 'scheduler', 'denoise']
const extras = computed(() => (props.template?.fields || []).filter((f) => !DEDICATED.includes(f)))
function isNum(f) { return typeof props.template?.defaults?.[f] === 'number' }
function labelFor(f) { return t.value[f] || t.value.th[f] || f }

const err = ref('')
const goLabel = computed(() => ({ video: t.value.generateVideo, model: t.value.generateModel }[props.template?.media]
  || t.value.generate))

function go() {
  // Only prompt-taking templates are checked; the 3D chain is driven by an image.
  if (has('prompt') && !props.params.prompt?.trim()) { err.value = t.value.needPrompt; return }
  err.value = ''
  emit('submit')
}
</script>

<template>
  <section class="card panel">
    <h2>{{ t.paramTitle }}</h2>
    <p v-if="err" class="drift">{{ err }}</p>

    <label v-if="has('unet')">{{ t.model }}
      <select v-model="params.unet">
        <option v-for="u in unets" :key="u.name" :value="u.name" :title="tip(u.name)">
          {{ u.name.replace('.safetensors', '') }} · {{ badge(u.name) }}
        </option>
      </select>
    </label>

    <label v-if="has('prompt')">{{ t.prompt }}<textarea v-model="params.prompt" rows="3" /></label>
    <label v-if="has('negative')">{{ t.negative }}<textarea v-model="params.negative" rows="3" /></label>

    <div v-if="extras.length" class="grp">
      <label v-for="f in extras" :key="f">{{ labelFor(f) }}
        <input v-model="params[f]" :type="isNum(f) ? 'number' : 'text'" />
      </label>
    </div>

    <div class="grp">
      <label v-if="has('width')" class="grow">{{ t.size }}
        <select :value="sizeKey" @change="pickSize($event.target.value)">
          <option v-for="[w, h] in SIZES" :key="w + 'x' + h" :value="w + 'x' + h">{{ w}} × {{ h }}</option>
        </select>
      </label>
      <label v-if="has('batch')" class="num">{{ t.batchN }}
        <input v-model.number="params.batch" type="number" min="1" max="4" />
      </label>
    </div>

    <div class="slider" v-if="has('steps')">
      <span>{{ t.steps }}</span>
      <input v-model.number="params.steps" type="range" min="1" max="50" />
      <input v-model.number="params.steps" type="number" min="1" max="50" class="box" />
    </div>
    <div class="slider" v-if="has('cfg')">
      <span>{{ t.cfg }}</span>
      <input v-model.number="params.cfg" type="range" min="0.5" max="10" step="0.1" />
      <input v-model.number="params.cfg" type="number" min="0.5" max="10" step="0.1" class="box" />
    </div>

    <label v-if="has('seed')" class="seedrow">{{ t.seed }}
      <input v-model.number="params.seed" type="number" min="-1" />
      <button class="ghost sm" @click="params.seed = Math.floor(Math.random() * 1e9)">↻</button>
    </label>

    <button class="ghost full" @click="adv = !adv">{{ t.advanced }} {{ adv ? '▴' : '▾' }}</button>
    <div v-show="adv" class="adv">
      <label class="inrow">{{ t.shift }}<input v-model.number="params.shift" type="number" step="0.5" /></label>
      <label class="inrow">{{ t.sampler }}<input v-model="params.sampler" /></label>
      <label class="inrow">{{ t.scheduler }}<input v-model="params.scheduler" /></label>
      <label class="inrow">{{ t.denoise }}<input v-model.number="params.denoise" type="number" step="0.05" /></label>
      <p class="hint">高级参数只在模板声明了对应节点时才生效。</p>
    </div>

    <button class="go" :disabled="busy" @click="go">▶ {{ busy ? t.generating : goLabel }}</button>
  </section>
</template>
