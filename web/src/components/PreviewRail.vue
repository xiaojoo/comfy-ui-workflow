<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from '../i18n'

const props = defineProps({ task: Object })
const emit = defineEmits(['favorite'])
const { t } = useI18n()

const outputs = computed(() => props.task?.outputs || [])
const picked = ref(0)
watch(() => props.task?.id, () => { picked.value = 0 })
const current = computed(() => outputs.value[Math.min(picked.value, outputs.value.length - 1)] || null)

// By extension, not by task.media: the 3D chain emits a glb alongside two png
// renders, so one label for the whole task would render the mesh as an image.
function kindOf(f) {
  const e = (f?.filename || '').split('.').pop()?.toLowerCase()
  return e === 'mp4' || e === 'webm' ? 'video' : e === 'glb' || e === 'gltf' ? 'model' : 'image'
}
const kind = computed(() => kindOf(current.value))

function local(iso) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour12: false }) : ''
}
const running = computed(() => ['queued', 'running'].includes(props.task?.state))
</script>

<template>
  <aside class="rail">
    <section class="card">
      <h2>{{ t.preview }}</h2>
      <div v-if="!current" class="empty tall">{{ t.noPreview }}</div>
      <template v-else>
        <div class="hero-img checker">
          <video v-if="kind === 'video'" :src="current.url" controls autoplay loop muted :poster="null" />
          <img v-else-if="kind === 'image'" :src="current.url" :alt="current.filename" />
          <div v-else class="modelcard">
            <span class="big">GLB</span>
            <code>{{ current.filename }}</code>
            <p>网格文件需下载后在查看器中打开；本页不内置 3D 查看。</p>
          </div>
        </div>
        <div v-if="outputs.length > 1" class="variants">
          <button v-for="(o, i) in outputs" :key="o.filename" :class="{ on: i === picked }"
                  @click="picked = i">
            <img v-if="kindOf(o) === 'image'" :src="o.url" :alt="o.filename" />
            <span v-else class="ext">{{ o.filename.split('.').pop() }}</span>
          </button>
        </div>
        <dl class="facts">
          <div><dt>{{ t.taskId }}</dt><dd>{{ task.ref }}</dd></div>
          <div><dt>{{ t.modelUsed }}</dt><dd>{{ task.model }}</dd></div>
          <div><dt>{{ t.created }}</dt><dd>{{ local(task.created_at) }}</dd></div>
          <div><dt>{{ t.elapsed }}</dt><dd>{{ task.seconds ? task.seconds.toFixed(1) + 's' : '—' }}</dd></div>
        </dl>
        <div class="rail-actions">
          <a class="ghost btn" :href="current.url" :download="current.filename">⬇ {{ t.download }}</a>
          <button :class="{ fav: task.favorite }" @click="emit('favorite', !task.favorite)">
            ☆ {{ task.favorite ? t.favorited : t.favorite }}
          </button>
        </div>
      </template>
    </section>

    <section v-if="task" class="card">
      <h2>{{ t.taskStatus }}</h2>
      <p class="statusline">
        <span class="chip" :class="task.state">{{ t.state[task.state] || task.state }}</span>
        <span v-if="task.error" class="err">{{ task.error }}</span>
      </p>
      <div class="bar"><i :style="{ width: task.progress + '%' }" /></div>
      <p class="pct">{{ task.progress }}%<span v-if="running" class="spin" /></p>
    </section>

    <section v-if="task?.log?.length" class="card">
      <h2>{{ t.execLog }}</h2>
      <ul class="log">
        <li v-for="(e, i) in task.log" :key="i" :class="{ last: i === task.log.length - 1 }">
          <time>{{ local(e.ts) }}</time><span>{{ e.msg }}</span>
        </li>
      </ul>
    </section>
  </aside>
</template>
