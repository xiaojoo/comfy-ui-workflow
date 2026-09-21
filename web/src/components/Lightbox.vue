<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({ title: String, code: String, file: Object })
const emit = defineEmits(['close'])
const { t } = useI18n()

// By extension, not by task.media: the 3D chain emits a glb alongside two png renders,
// so one label for the whole task would render the mesh as an image.
function extOf(f) { return (f?.filename || '').split('.').pop().toLowerCase() }
function kindOf(f) { return ['mp4', 'webm'].includes(extOf(f)) ? 'video'
  : ['glb', 'gltf'].includes(extOf(f)) ? 'model' : 'image' }

function onKey(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div class="lightbox" @click.self="emit('close')">
      <div class="lbbox">
        <header>
          <b>{{ title }}</b>
          <span class="mono">{{ code }}</span>
          <span class="sp" />
          <a class="iconbtn" :href="file.url" :download="file.filename" :title="t.download">⬇</a>
          <button class="iconbtn" :title="t.close" @click="emit('close')">✕</button>
        </header>
        <video v-if="kindOf(file) === 'video'" :src="file.url" controls autoplay muted playsinline />
        <img v-else-if="kindOf(file) === 'image'" :src="file.url" :alt="file.filename" />
        <p v-else class="lbnote">{{ t.meshNote }}</p>
      </div>
    </div>
  </Teleport>
</template>
