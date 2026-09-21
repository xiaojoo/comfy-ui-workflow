<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../i18n'

const props = defineProps({ batchId: Number, asset: Object })
const { t } = useI18n()
const stage = ref('flat')
const svg = ref('')
const err = ref('')

// As an <img>, not v-html: a data URI gives the SVG its own rendering context,
// so a stray <script> in a vector file cannot run against this page.
const dataUri = computed(() => 'data:image/svg+xml;utf8,' + encodeURIComponent(svg.value))

async function load() {
  if (!props.asset) return
  err.value = ''
  try {
    svg.value = (await api.svg(props.batchId, props.asset.id, stage.value)).svg
  } catch (e) {
    svg.value = ''
    err.value = e.message
  }
}
watch(() => [props.asset?.id, stage.value], load, { immediate: true })

const sizes = [24, 32, 48, 96]
</script>

<template>
  <section v-if="asset" class="preview">
    <header>
      <h2>{{ t.previewTitle }} · {{ asset.name }}</h2>
      <div class="tabs">
        <button v-for="s in ['raw', 'norm', 'flat']" :key="s" :class="{ on: stage === s }" @click="stage = s">
          {{ t.stages[s] }}
        </button>
      </div>
    </header>
    <p class="hint">{{ t.previewHint }}</p>
    <p v-if="err" class="drift">{{ err }}</p>
    <div v-else class="renders">
      <figure v-for="s in sizes" :key="s">
        <div class="checker" :style="{ width: s + 'px', height: s + 'px' }">
          <img :src="dataUri" :width="s" :height="s" :alt="asset.name" />
        </div>
        <figcaption>{{ s }}px</figcaption>
      </figure>
    </div>
  </section>
</template>
