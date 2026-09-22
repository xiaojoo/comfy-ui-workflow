<script setup>
import { computed, ref } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { useI18n } from '../i18n'

// Rendered inside the Vue Flow slot, so the props are the library's NodeProps: `data`
// carries everything the page authored for this step.
const props = defineProps({ id: String, selected: Boolean,
                            data: { type: Object, required: true } })
const emit = defineEmits(['edit', 'del', 'zoom'])
const { t, lang } = useI18n()

const tpl = computed(() => props.data.tpl)
const name = computed(() => (lang.value === 'zh' ? tpl.value.name : tpl.value.name_en) || tpl.value.name)
const model = computed(() => (lang.value === 'zh' ? tpl.value.model : tpl.value.model_en) || tpl.value.model)
const step = computed(() => props.data.run || {})
const state = computed(() => step.value.state || 'pending')
const inPorts = computed(() => tpl.value.ports.in)

// The picture this step produced. `outputs` keeps its slot positions even when a file
// was deleted, so the raw index is carried through and only the display filters -- the
// wire's 「第几张」 is that raw index, and renumbering here would silently repoint it.
const outs = computed(() => (step.value.outputs || []).map((o, i) => ({ ...o, i })))
const gone = computed(() => !!outs.value[props.data.pickIdx ?? 0]?.deleted)
const shot = computed(() => {
  const live = outs.value.filter((o) => !o.deleted)
  if (!live.length || gone.value) return null
  const want = outs.value[props.data.pickIdx ?? 0]
  const at = want ? live.findIndex((o) => o.i === want.i) : -1
  return { ...live[at < 0 ? 0 : at], all: live }
})
const isClip = computed(() => /\.(mp4|webm|mov)$/i.test(shot.value?.filename || ''))
const changed = computed(() => props.data.changed || [])
// What this step was told to do beyond one plain run, shown on the card so the plan is
// readable without opening the drawer.
const pol = computed(() => {
  const d = props.data, out = []
  if ((d.repeat || 1) > 1) out.push(t.value.canvasBadgeRepeat.replace('{n}', d.repeat))
  if (d.retries) out.push(t.value.canvasBadgeRetry.replace('{n}', d.retries))
  if (d.on_error === 'skip') out.push(t.value.canvasBadgeSkip)
  return out
})
// The ✕ is revealed under the pointer, not by :hover -- Chrome was measured holding
// stale :hover sets across siblings in this app already.
const hot = ref(false)
</script>

<template>
  <div class="fn" :class="[`s-${state}`, { on: selected, hot }]"
       @pointerenter="hot = true" @pointerleave="hot = false">
    <Handle v-for="(p, i) in inPorts" :key="p.name" type="target" :position="Position.Left"
            :id="p.name" class="port" :style="{ top: `${34 + i * 22}px` }"
            :title="`${t.portIn} ${p.name} · ${t.portTypes[p.type]}`" />

    <header>
      <b class="ord">{{ data.order }}</b>
      <span class="nm">{{ name }}</span>
      <button class="x" :title="t.canvasDelStep" @click.stop="emit('del', id)">✕</button>
    </header>

    <p class="mo">{{ model }}<span v-if="tpl.spec"> · {{ tpl.spec }}</span></p>

    <p v-if="changed.length" class="ch">
      <i v-for="c in changed" :key="c.k">{{ c.k }} {{ c.v }}</i>
    </p>
    <p v-else class="ch def">{{ t.canvasUsesDefaults }}</p>
    <p v-if="pol.length" class="pol"><i v-for="p in pol" :key="p">{{ p }}</i></p>

    <div v-if="inPorts.length" class="pins">
      <span v-for="p in inPorts" :key="p.name" class="pin">{{ p.name }}</span>
    </div>

    <div v-if="shot" class="thumb" @click.stop="emit('zoom', { shot, node: id })">
      <video v-if="isClip" :src="shot.url" preload="metadata" muted playsinline />
      <img v-else :src="shot.url" :alt="shot.filename" loading="lazy" />
      <span v-if="isClip" class="ply">▶</span>
    </div>
    <p v-else-if="gone" class="none">{{ t.deletedRun }}</p>

    <footer>
      <span class="dot" />
      <span class="st">{{ t.canvasState[state] }}</span>
      <span v-if="state === 'running'" class="pg">{{ step.progress }}%</span>
      <span v-else-if="step.seconds" class="pg">{{ step.seconds.toFixed(1) }}s</span>
      <!-- Only worth saying when it retried: the number is the reason a step took twice
           as long as its own budget. -->
      <span v-if="step.attempts > 1" class="pg">{{ t.canvasTried }} {{ step.attempts }}</span>
      <button class="ed" @click.stop="emit('edit', id)">{{ t.canvasParams }}</button>
    </footer>
    <p v-if="step.error" class="err">{{ step.error }}</p>

    <Handle type="source" :position="Position.Right" :id="tpl.media" class="port out"
            :title="`${t.portOut} ${tpl.media}`" />
  </div>
</template>
