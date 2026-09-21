<script setup>
import { computed, nextTick, onBeforeUnmount, ref, useId } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, default: () => [] },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

// The panel is teleported to <body> on purpose: the parameter drawer scrolls inside
// an overflow container, so a list rendered in place would be clipped at its edge.
const uid = useId()
const ROW = 32
// The panel's own 6px padding (x2) and 1px border (x2): box-sizing is border-box, so
// these live inside max-height. Leaving the border out made a list that fits exactly
// overflow by 2px and paint a scrollbar for no reason.
const INSET = 14
const MAXH = 268
const btn = ref(null)
const pop = ref(null)
const open = ref(false)
const active = ref(0)
const box = ref({})

const shown = computed(() => props.options.find((o) => o.value === props.modelValue)?.label ?? '—')
const optId = (i) => `${uid}-o${i}`

function place() {
  const r = btn.value.getBoundingClientRect()
  const need = props.options.length * ROW + INSET
  const below = window.innerHeight - r.bottom - 12
  const above = r.top - 12
  const up = below < Math.min(MAXH, need) && above > below
  const room = Math.max(96, Math.min(MAXH, need, up ? above : below))
  box.value = {
    left: `${r.left}px`, width: `${r.width}px`, maxHeight: `${room}px`,
    top: `${up ? r.top - room - 4 : r.bottom + 4}px`,
  }
}

async function show() {
  active.value = Math.max(0, props.options.findIndex((o) => o.value === props.modelValue))
  open.value = true
  await nextTick()
  place()
  // An 11-weight list opened at the top hides the one in use; start on it. The
  // max-height that makes the panel scrollable is only in the DOM after place()
  // has been rendered, so the scroll waits for that tick.
  await nextTick()
  document.getElementById(optId(active.value))?.scrollIntoView({ block: 'nearest' })
  document.addEventListener('pointerdown', outside, true)
  // Any scroll under the trigger moves it away from a fixed panel, so the list goes
  // with it rather than floating over the row it was opened from. Scrolling the
  // panel itself is the list working as intended, so it is let through.
  document.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', hide)
}

function onScroll(e) {
  if (e.target !== pop.value) hide()
}

function hide() {
  open.value = false
  document.removeEventListener('pointerdown', outside, true)
  document.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('resize', hide)
}

function outside(e) {
  if (!e.target.closest('.sel, .sel-pop')) hide()
}

function pick(i) {
  const o = props.options[i]
  if (o) emit('update:modelValue', o.value)
  hide()
}

function onKey(e) {
  const n = props.options.length
  if (!open.value) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
      e.preventDefault()
      show()
      if (e.key === 'ArrowUp') active.value = n - 1
    }
    return
  }
  if (e.key === 'Escape') { e.preventDefault(); hide() }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = (active.value + (e.key === 'ArrowDown' ? 1 : n - 1)) % n
    nextTick(() => document.getElementById(optId(active.value))?.scrollIntoView({ block: 'nearest' }))
  } else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(active.value) }
  else if (e.key === 'Tab') hide()
}

onBeforeUnmount(hide)
</script>

<template>
  <button ref="btn" type="button" class="sel" :class="{ on: open }" :aria-label="label"
          aria-haspopup="listbox" :aria-expanded="open"
          :aria-activedescendant="open ? optId(active) : undefined"
          @click="open ? hide() : show()" @keydown="onKey">
    <span class="v">{{ shown }}</span>
    <svg class="caret" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.6 4.6 6 8l3.4-3.4" /></svg>
  </button>

  <Teleport to="body">
    <div v-if="open" ref="pop" class="sel-pop" :style="box" role="listbox" :aria-label="label">
      <button v-for="(o, i) in options" :id="optId(i)" :key="o.value" type="button" role="option"
              :class="{ on: o.value === modelValue, act: i === active }" :aria-selected="o.value === modelValue"
              :title="o.hint" @mouseenter="active = i" @click="pick(i)">{{ o.label }}</button>
    </div>
  </Teleport>
</template>
