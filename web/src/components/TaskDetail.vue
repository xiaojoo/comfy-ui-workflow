<script setup>
import { computed, ref } from 'vue'
import { useI18n } from '../i18n'
import Lightbox from './Lightbox.vue'

const props = defineProps({ task: Object, name: String })
const emit = defineEmits(['close'])
const { t } = useI18n()

const big = ref(null)

const running = computed(() => ['queued', 'running'].includes(props.task.state))

// created_at / finished_at are naive UTC out of the database while a log line's ts
// carries its own offset; reading both with new Date() lands eight hours off.
function asDate(iso) {
  if (!iso) return null
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
}
function clock(iso) {
  const d = asDate(iso)
  return d ? d.toLocaleString([], { month: '2-digit', day: '2-digit',
                                     hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'
}
function hhmm(iso) {
  const d = asDate(iso)
  return d ? d.toLocaleTimeString([], { hour12: false }) : '—'
}

// prefix is the engine's own output subfolder, set by POST /tasks and not a knob
// anyone can turn, so it is the one stored parameter the detail hides.
const HIDDEN = ['prefix']
const rows = computed(() => Object.entries(props.task.params || {}).filter(([k]) => !HIDDEN.includes(k))
  .map(([k, v]) => ({ k, label: t.value.th[k] || t.value[k] || k, value: String(v) })))

// A 2000-char prompt would otherwise push the rest of the drawer out of view.
const isLong = (v) => v.length > 80

function extOf(f) { return (f?.filename || '').split('.').pop().toLowerCase() }
function kindOf(f) { return ['mp4', 'webm'].includes(extOf(f)) ? 'video'
  : ['glb', 'gltf'].includes(extOf(f)) ? 'model' : 'image' }
</script>

<template>
  <aside class="drawer">
    <header class="dhead">
      <span class="dico">◷</span>
      <div class="dtitle">
        <h2>{{ name || task.template }}<span class="chip" :class="task.state">{{ t.state[task.state] || task.state }}</span></h2>
        <p>{{ task.title || task.ref }}</p>
      </div>
      <button class="icon ghost" :title="t.close" @click="emit('close')">✕</button>
    </header>

    <div class="dbody">
      <p v-if="task.error" class="drift">{{ task.error }}</p>

      <template v-if="running">
        <div class="bar"><i :style="{ width: task.progress + '%' }" /></div>
        <p class="pct">{{ task.progress }}%</p>
      </template>

      <dl class="facts">
        <div><dt>{{ t.taskId }}</dt><dd>{{ task.ref }}</dd></div>
        <div><dt>{{ t.modelUsed }}</dt><dd>{{ task.model }}</dd></div>
        <div><dt>{{ t.created }}</dt><dd>{{ clock(task.created_at) }}</dd></div>
        <div><dt>{{ t.finished }}</dt><dd>{{ clock(task.finished_at) }}</dd></div>
        <div><dt>{{ t.elapsed }}</dt><dd>{{ task.seconds != null ? task.seconds.toFixed(1) + 's' : '—' }}</dd></div>
        <div v-if="task.comfy_id"><dt>{{ t.comfyId }}</dt><dd>{{ task.comfy_id }}</dd></div>
      </dl>

      <h3 class="dsec">{{ t.th.params }}</h3>
      <dl class="plist">
        <div v-for="r in rows" :key="r.k">
          <dt>{{ r.label }}</dt>
          <dd :class="{ clip: isLong(r.value) }">{{ r.value }}</dd>
        </div>
      </dl>

      <h3 class="dsec">{{ t.variants }}</h3>
      <p v-if="!task.outputs?.length" class="hint">{{ t.noOutput }}</p>
      <div v-else class="files">
        <figure v-for="o in task.outputs" :key="o.url" class="file">
          <div class="thumb" :title="t.enlargeFile" @click="big = o">
            <video v-if="kindOf(o) === 'video'" :src="o.url" preload="metadata" muted />
            <img v-else-if="kindOf(o) === 'image'" :src="o.url" :alt="o.filename" loading="lazy" />
            <span v-else class="ext">{{ extOf(o) }}</span>
            <span v-if="kindOf(o) === 'video'" class="play">▶</span>
          </div>
          <a class="iconbtn dl" :href="o.url" :download="o.filename" :title="t.download">⬇</a>
          <figcaption><span class="fnm">{{ o.filename }}</span></figcaption>
        </figure>
      </div>

      <h3 class="dsec">{{ t.execLog }}</h3>
      <p v-if="!task.log?.length" class="hint">{{ t.noLog }}</p>
      <ul v-else class="log">
        <li v-for="(e, i) in task.log" :key="i" :class="{ last: i === task.log.length - 1 }">
          <time>{{ hhmm(e.ts) }}</time><span>{{ e.msg }}</span>
        </li>
      </ul>
    </div>
  </aside>

  <Lightbox v-if="big" :title="big.filename" :code="task.ref" :file="big" @close="big = null" />
</template>
