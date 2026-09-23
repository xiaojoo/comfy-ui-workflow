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
// What the delivery gate said about the last picture this step made. The record is the
// server's -- the columns, the preset that carried it, the seconds -- so the card cannot
// claim a verdict the ruler did not give.
const gate = computed(() => step.value.gate || null)
// What this step was told to do beyond one plain run, shown on the card so the plan is
// readable without opening the drawer.
const pol = computed(() => {
  const d = props.data, out = []
  if ((d.repeat || 1) > 1) out.push(t.value.canvasBadgeRepeat.replace('{n}', d.repeat))
  if (d.retries) out.push(t.value.canvasBadgeRetry.replace('{n}', d.retries))
  if (d.on_error === 'skip') out.push(t.value.canvasBadgeSkip)
  if (d.gate === 'sweep') out.push(t.value.canvasBadgeGateSweep)
  else if (d.gate === 'check') out.push(t.value.canvasBadgeGateCheck)
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

    <!-- The gate's verdict on this step's last picture, and one download per SVG it
         accepted. The failing columns are only spelled out when the card is not already
         saying them in red below. -->
    <p v-if="gate" class="gate" :class="gate.verdict === 'PASS' ? 'ok' : 'no'">
      <b>{{ gate.verdict }}</b>
      <i v-if="gate.verdict === 'PASS' && gate.presets.length">{{ t.canvasGateBy }} {{ gate.presets.join('/') }}</i>
      <i v-if="gate.bad.length">{{ t.canvasGateBad.replace('{n}', gate.bad.length)
                                        .replace('{N}', gate.bad.length + gate.svgs.length) }}</i>
      <i>{{ gate.seconds }}s</i>
      <a v-for="(s, i) in gate.svgs" :key="s.href" class="dl" :href="s.href" :download="s.dl"
         :title="gate.svgs.length > 1 ? t.canvasGateSvgN.replace('{n}', i + 1) : t.canvasGateSvg"
         @click.stop>⤓ {{ gate.svgs.length > 1 ? i + 1 : t.canvasGateSvg }}</a>
    </p>
    <p v-if="gate && gate.verdict !== 'PASS' && !step.error" class="why">{{ gate.fails.join('、') }}</p>

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
    <!-- The condition ports: a wire between these two carries no picture, only "run this
         step when that one ended this way". They sit at the bottom of the card, away from
         the media ports -- and they have to move `top`, because the library pins the
         vertical centre with `top: 50%` and a `bottom` offset is then simply ignored. -->
    <Handle type="target" :position="Position.Left" id="@ctl" class="port ctl"
            :style="{ top: 'calc(100% - 14px)' }" :title="t.canvasCtlIn" />
    <Handle type="source" :position="Position.Right" id="@ctl" class="port ctl out"
            :style="{ top: 'calc(100% - 14px)' }" :title="t.canvasCtlOut" />
  </div>
</template>
