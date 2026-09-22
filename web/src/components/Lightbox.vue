<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import { useI18n } from '../i18n'
import ModelView from './ModelView.vue'

// `task` is the row the files came from: with it the view offers permanent removal,
// without it (an engine input file, a local blob) there is nothing here to delete.
const props = defineProps({ title: String, code: String, files: Array, index: Number, task: Number })
const emit = defineEmits(['close', 'update:index', 'deleted'])
const { t } = useI18n()

const file = computed(() => props.files[props.index] || null)

// By extension, not by task.media: the 3D chain emits a glb alongside two png renders,
// so one label for the whole task would render the mesh as an image.
function extOf(f) { return (f?.filename || '').split('.').pop().toLowerCase() }
function kindOf(f) { return ['mp4', 'webm'].includes(extOf(f)) ? 'video'
  : ['glb', 'gltf'].includes(extOf(f)) ? 'model' : 'image' }

// A run of two or three images is stepped through, not paginated, so it wraps at both ends.
function step(d) { emit('update:index', (props.index + d + props.files.length) % props.files.length) }

// The two arrows are a pair in one wrapper, and Chrome was measured holding both in its
// :hover set at once, so the highlight follows the pointer events instead.
const hot = ref(-1)

function onKey(e) {
  if (e.key === 'Escape') { if (ask.value) ask.value = false; else emit('close'); return }
  if (ask.value || props.files.length < 2) return
  // Once the player has focus, Left/Right belong to it: stepping the file then would
  // seek the clip and swap it away in the same keypress.
  if (e.target?.tagName === 'VIDEO') return
  if (e.key === 'ArrowLeft') step(-1)
  else if (e.key === 'ArrowRight') step(1)
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))

const ask = ref(false)
const busy = ref(false)
const oops = ref('')

// The row's own index travels with the entry, not its position on screen: a removed
// slot stays in the row so an input binding made earlier still means the same file.
async function drop() {
  busy.value = true
  oops.value = ''
  try {
    emit('deleted', await api.deleteOutput(props.task, { index: file.value.i, filename: file.value.filename }))
    ask.value = false
  } catch (e) {
    oops.value = `${e.status ?? ''} ${e.message}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="lightbox" @click.self="emit('close')">
      <div class="lbbox">
        <div class="lbstage">
          <header>
            <b>{{ title }}</b>
            <span class="mono">{{ code }}</span>
            <span v-if="files.length > 1" class="mono lbpos">{{ index + 1 }} / {{ files.length }}</span>
            <span class="sp" />
            <a class="iconbtn" :href="file.url" :download="file.filename" :title="t.download">⬇</a>
            <button v-if="task" class="iconbtn del" :title="t.delImage" @click="ask = true; oops = ''">
              <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"
                   ><path d="M3 4h10M6.4 4V2.4h3.2V4M4.6 4l.7 9.2h5.4L11.4 4M6.7 6.6v4.4M9.3 6.6v4.4"
                          fill="none" stroke="currentColor" stroke-width="1.2"/></svg>
            </button>
            <button class="iconbtn" :title="t.close" @click="emit('close')">✕</button>
          </header>
          <video v-if="kindOf(file) === 'video'" :key="file.url" :src="file.url" controls autoplay muted playsinline />
          <img v-else-if="kindOf(file) === 'image'" :key="file.url" :src="file.url" :alt="file.filename" />
          <ModelView v-else :key="file.url" :src="file.url" />
          <button v-if="files.length > 1" class="carrow prev" :class="{ hot: hot === 0 }"
                  :title="t.prevImg" :aria-label="t.prevImg"
                  @pointerenter="hot = 0" @pointerleave="hot = -1" @click="step(-1)">‹</button>
          <button v-if="files.length > 1" class="carrow next" :class="{ hot: hot === 1 }"
                  :title="t.nextImg" :aria-label="t.nextImg"
                  @pointerenter="hot = 1" @pointerleave="hot = -1" @click="step(1)">›</button>

          <div v-if="ask" class="lbask" @click.stop>
            <p class="q">{{ t.delAsk }}</p>
            <p class="mono fnm">{{ file.filename }}</p>
            <p class="hint">{{ t.delWarn }}</p>
            <p v-if="oops" class="err">{{ oops }}</p>
            <div class="acts">
              <button class="ghost sm" :disabled="busy" @click="ask = false">{{ t.cancel }}</button>
              <button class="sm del" :disabled="busy" @click="drop">{{ busy ? t.deleting : t.delConfirm }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
