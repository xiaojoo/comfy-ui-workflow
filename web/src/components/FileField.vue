<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from '../i18n'
import Lightbox from './Lightbox.vue'

const props = defineProps({ modelValue: String, label: String, kind: { type: String, default: 'image' } })
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()

const VID_EXT = /\.(mp4|webm|mov)$/i
const IMG_EXT = /\.(png|jpe?g|webp|bmp|gif)$/i
const el = ref(null)
const busy = ref(false)
const err = ref('')
const big = ref(false)
// The engine's own URL is the only honest preview: it proves the file landed in the
// input directory, not just that the browser held the bytes.
const served = (name) => `/comfy/view?filename=${encodeURIComponent(name)}&subfolder=&type=input`
const local = ref('')
const localName = ref('')
const name = computed(() => localName.value || props.modelValue || '')
const src = computed(() => local.value || (props.modelValue ? served(props.modelValue) : ''))
const isVid = computed(() => VID_EXT.test(name.value))

async function send(file) {
  err.value = ''
  if (props.kind === 'video' ? !VID_EXT.test(file.name) : !IMG_EXT.test(file.name)) {
    err.value = props.kind === 'video' ? t.value.needVideo : t.value.needImage
    return
  }
  busy.value = true
  local.value = URL.createObjectURL(file)
  localName.value = file.name
  try {
    const fd = new FormData()
    fd.append('image', file, file.name)
    fd.append('type', 'input')
    fd.append('overwrite', 'true')
    const r = await fetch('/comfy/upload/image', { method: 'POST', body: fd })
    const d = await r.json().catch(() => null)
    if (!r.ok || !d?.name) throw new Error(`${r.status} ${d?.detail?.message || d?.error || r.statusText}`)
    emit('update:modelValue', d.name)
  } catch (e) {
    err.value = `${t.value.uploadFail}：${e.message}`
  } finally {
    busy.value = false
    dropLocal()
  }
}

function dropLocal() {
  if (!local.value) return
  URL.revokeObjectURL(local.value)
  local.value = ''
  localName.value = ''
}

function onChange() {
  const f = el.value?.files?.[0]
  if (f) send(f)
}

function onDrop(e) {
  const f = e.dataTransfer?.files?.[0]
  if (f) send(f)
}

// A name that came back from a stored run is not a file we hold, so the preview is
// whatever the engine serves -- and if it no longer exists, say so instead of showing
// a broken frame.
const broken = ref(false)
watch(() => [props.modelValue, local.value], () => { broken.value = false })
onBeforeUnmount(dropLocal)
</script>

<template>
  <div class="ff" :class="{ busy }">
    <button type="button" class="ghost ff-pick" :disabled="busy" :title="name || t.chooseFile"
            @click="el?.click()" @dragover.prevent @drop.prevent="onDrop">
      <span class="ff-name">{{ busy ? t.uploading : (name || t.chooseFile) }}</span>
      <span class="ff-hint">{{ t.dropHere }}</span>
    </button>
    <button type="button" class="ff-prev" :disabled="!src || broken" :title="t.enlargeFile"
            @click="big = true">
      <video v-if="src && !broken && isVid" :src="src" preload="metadata" muted />
      <img v-else-if="src && !broken" :src="src" :alt="name || label" @error="broken = true" />
      <span v-if="!src || broken" class="ff-glyph">{{ broken ? '?' : '＋' }}</span>
    </button>
    <input ref="el" class="ff-input" type="file" :accept="kind === 'video' ? 'video/mp4,video/webm,video/quicktime' : 'image/*'"
           :aria-label="label" @change="onChange" />
  </div>
  <p v-if="err" class="err ff-err">{{ err }}</p>

  <Lightbox v-if="big && src && !broken" :title="name" code="ComfyUI input"
            :file="{ url: src, filename: name }" @close="big = false" />
</template>
