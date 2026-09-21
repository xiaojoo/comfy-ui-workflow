<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: [Number, String], default: '' },
  min: { type: Number, default: -Infinity },
  max: { type: Number, default: Infinity },
  step: { type: Number, default: 1 },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

// What is being typed, kept separate from the committed number so a half-written
// value ("-", "1.") stays on screen instead of snapping to 0 or NaN.
const text = ref('')
const num = computed(() => Number(props.modelValue))
const shown = computed(() => (text.value === '' ? props.modelValue : text.value))

// 0.1 + 0.2 has to be quantised or the CFG box would drift to 1.1000000000000003.
const decimals = computed(() => (String(props.step).split('.')[1] || '').length)
const quant = (v) => +v.toFixed(decimals.value)
const clamp = (v) => Math.min(props.max, Math.max(props.min, v))

function bump(dir) {
  const base = Number.isFinite(num.value) ? num.value : (Number.isFinite(props.min) ? props.min : 0)
  emit('update:modelValue', quant(clamp(base + dir * props.step)))
}

function onInput(e) {
  text.value = e.target.value
  const v = Number(e.target.value)
  if (e.target.value !== '' && Number.isFinite(v)) emit('update:modelValue', v)
}

function commit() {
  const v = Number(text.value)
  if (text.value !== '' && Number.isFinite(v)) emit('update:modelValue', quant(clamp(v)))
  text.value = ''
}

const atMin = computed(() => Number.isFinite(num.value) && num.value <= props.min)
const atMax = computed(() => Number.isFinite(num.value) && num.value >= props.max)

// Chrome's :hover node list was measured keeping *both* sibling buttons lit after a
// single pointer move (elementFromPoint and pointerover both name only the one under
// the cursor), so the highlight is driven by the pointer events, which are correct.
const hot = ref(-1)
</script>

<template>
  <span class="num">
    <button type="button" class="sbtn" :class="{ hot: hot === 0 }" :disabled="atMin" :aria-label="`${label} -${step}`"
            @pointerenter="hot = 0" @pointerleave="hot = -1" @click="bump(-1)">−</button>
    <input :value="shown" type="number" :min="min" :max="max" :step="step" :aria-label="label"
           inputmode="decimal" @input="onInput" @blur="commit"
           @keydown.up.prevent="bump(1)" @keydown.down.prevent="bump(-1)" />
    <button type="button" class="sbtn" :class="{ hot: hot === 1 }" :disabled="atMax" :aria-label="`${label} +${step}`"
            @pointerenter="hot = 1" @pointerleave="hot = -1" @click="bump(1)">+</button>
  </span>
</template>
