<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../i18n'
import Lightbox from './Lightbox.vue'

const props = defineProps({ task: Object, runs: Array, templates: Array, filtered: Boolean })
const emit = defineEmits(['favorite', 'pick', 'useforvideo'])
const { t } = useI18n()

// Which templates can take a figure as their first frame, asked of the template list
// rather than hardcoded. Only the first gets a button here -- with two H3 routes a second
// glyph in the corner would be two identical arrows, so the drawer carries the choice.
const videoTargets = computed(() => (props.templates || [])
  .filter((x) => x.media === 'video' && (x.fields || []).includes('image')))

// 做高清 targets, asked of the template list the same way: the enhance graphs name
// their input field after the medium, so the button follows the graph, not an id.
const hdImageTarget = computed(() => (props.templates || [])
  .find((x) => x.category === 'enhance' && (x.fields || []).includes('image')))
const hdVideoTarget = computed(() => (props.templates || [])
  .find((x) => (x.fields || []).includes('video')))

// 拿去改: the reference-driven graph, found the same way -- by the field it reads. The
// picked result becomes ref1, so a figure can be re-lit or re-composited without
// re-uploading it out of the engine's output folder by hand.
const editTarget = computed(() => (props.templates || [])
  .find((x) => (x.fields || []).includes('ref1')))

const outputs = computed(() => props.task?.outputs || [])
const picked = ref(0)
const tab = ref('preview')

// A run that was just submitted lands on 任务状态, which is the question being asked
// at that moment; a finished task opened from the list lands on its picture.
watch(() => props.task?.id, () => {
  picked.value = 0
  tab.value = ['queued', 'running'].includes(props.task?.state) ? 'status' : 'preview'
})
const current = computed(() => outputs.value[Math.min(picked.value, outputs.value.length - 1)] || null)

// ------------------------------------------------------------- the lazy line
const strip = ref(null)
const full = reactive({})       // run id -> its detail, fetched when the tile nears view
watch(() => props.task, (v) => { if (v) full[v.id] = v }, { immediate: true })
const pending = new Set()       // in flight, so two observer passes cannot double-fetch
const atStart = ref(true)
const atEnd = ref(false)
const overflowing = ref(false)
let io = null

async function fetchOne(id) {
  if (full[id] || pending.has(id)) return
  pending.add(id)
  try { full[id] = await api.task(id) } finally { pending.delete(id) }
}

function observe() {
  if (!io || !strip.value) return
  for (const el of strip.value.querySelectorAll('[data-run]')) io.observe(el)
  measure()
}

function measure() {
  const e = strip.value
  if (!e) return
  overflowing.value = e.scrollWidth - e.clientWidth > 2
  atStart.value = e.scrollLeft < 2
  atEnd.value = e.scrollLeft + e.clientWidth > e.scrollWidth - 2
}

function page(dir) {
  strip.value.scrollBy({ left: dir * strip.value.clientWidth * 0.8, behavior: 'smooth' })
}

const big = ref(null)

async function choose(row) {
  // First click on a tile selects it; clicking the one already selected opens it full
  // size, which is where a video actually plays.
  if (row.id !== props.task?.id) {
    await fetchOne(row.id)
    if (full[row.id]) emit('pick', full[row.id])
    return
  }
  if (current.value) big.value = row
}

const line = computed(() => (props.runs || []).map((r) => ({ id: r.id, run: r, task: full[r.id] || null })))
const nameOf = (row) => props.templates?.find((x) => x.id === (row.task?.template || row.run.template))?.name
  || row.run.template
function cover(row) {
  if (row.id === props.task?.id) return current.value
  return row.task?.outputs?.[0] || null
}

// By extension, not by task.media: the 3D chain emits a glb alongside two png
// renders, so one label for the whole task would render the mesh as an image.
function kindOf(f) { return extOf(f) === 'mp4' || extOf(f) === 'webm' ? 'video' : extOf(f) === 'glb' || extOf(f) === 'gltf' ? 'model' : 'image' }
function extOf(f) { return (f?.filename || '').split('.').pop().toLowerCase() }

// created_at / finished_at are naive UTC out of the database, while a log line's ts
// carries its own offset. Reading both with new Date() put the preview eight hours
// from the task table, so the missing zone is added back here and nowhere else.
function asDate(iso) {
  if (!iso) return null
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : iso + 'Z')
}
function clock(iso) {
  const d = asDate(iso)
  return d ? d.toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—'
}
function hhmm(iso) {
  const d = asDate(iso)
  return d ? d.toLocaleTimeString([], { hour12: false }) : '—'
}

const running = computed(() => ['queued', 'running'].includes(props.task?.state))

onMounted(() => {
  io = new IntersectionObserver((rows) => {
    for (const r of rows) if (r.isIntersecting) { fetchOne(+r.target.dataset.run); io.unobserve(r.target) }
  }, { rootMargin: '300px' })
  nextTick(observe)
  window.addEventListener('resize', measure)
})
onBeforeUnmount(() => {
  io?.disconnect()
  window.removeEventListener('resize', measure)
})
watch(() => [props.runs?.length, tab.value], () => nextTick(observe))
</script>

<template>
  <section class="card results">
    <div class="rtabs">
      <button v-for="k in ['preview', 'status', 'log']" :key="k" class="ghost sm" :class="{ on: tab === k }"
              @click="tab = k">
        {{ k === 'preview' ? t.preview : k === 'status' ? t.taskStatus : t.execLog }}
      </button>
    </div>

    <div v-if="tab === 'preview'" class="rbody">
      <p v-if="!line.length" class="empty">{{ filtered ? t.noRunsOf : t.noPreview }}</p>
      <template v-else>
        <div class="carousel">
          <button v-show="overflowing" class="carrow prev" :disabled="atStart" :aria-label="t.prevPage"
                  @click="page(-1)">‹</button>
          <div ref="strip" class="strip" @scroll.passive="measure">
            <figure v-for="row in line" :key="row.id" class="shot" :class="{ on: row.id === task?.id }"
                    :data-run="row.id" :title="row.id === task?.id ? t.enlarge : row.run.ref" @click="choose(row)">
              <div class="frame checker">
                <video v-if="cover(row) && kindOf(cover(row)) === 'video'" :src="cover(row).url"
                       preload="metadata" muted />
                <img v-else-if="cover(row) && kindOf(cover(row)) === 'image'" :src="cover(row).url"
                     :alt="cover(row).filename" loading="lazy" />
                <span v-else-if="cover(row)" class="ext">{{ extOf(cover(row)) }}</span>
                <span v-else class="none">{{ t.loading }}</span>
                <span v-if="cover(row) && kindOf(cover(row)) === 'video'" class="play">▶</span>

                <div v-if="row.id === task?.id && current" class="corner">
                  <a class="iconbtn" :href="current.url" :download="current.filename" :title="t.download">⬇</a>
                  <button class="iconbtn" :class="{ fav: task.favorite }"
                          :title="task.favorite ? t.favorited : t.favorite"
                          @click.stop="emit('favorite', !task.favorite)">
                    {{ task.favorite ? '★' : '☆' }}
                  </button>
                  <button v-if="videoTargets.length" v-show="kindOf(current) === 'image'"
                          class="iconbtn" :title="`${t.useForVideo} · ${videoTargets[0].name}`"
                          @click.stop="emit('useforvideo', { task, index: picked, target: videoTargets[0].id })">
                    ▷
                  </button>
                  <button v-if="hdImageTarget" v-show="kindOf(current) === 'image'"
                          class="iconbtn" :title="`${t.useForHD} · ${hdImageTarget.name}`"
                          @click.stop="emit('useforvideo', { task, index: picked, target: hdImageTarget.id })">
                    ✦
                  </button>
                  <button v-if="editTarget" v-show="kindOf(current) === 'image'"
                          class="iconbtn" :title="`${t.useForEdit} · ${editTarget.name}`"
                          @click.stop="emit('useforvideo', { task, index: picked, target: editTarget.id })">
                    ✎
                  </button>
                  <button v-if="hdVideoTarget" v-show="kindOf(current) === 'video'"
                          class="iconbtn" :title="`${t.useForHD} · ${hdVideoTarget.name}`"
                          @click.stop="emit('useforvideo', { task, index: picked, target: hdVideoTarget.id })">
                    ✦
                  </button>
                </div>
              </div>
              <figcaption>
                <b>{{ nameOf(row) }}</b>
                <span>{{ clock(row.run.created_at) }}</span>
              </figcaption>
            </figure>
          </div>
          <button v-show="overflowing" class="carrow next" :disabled="atEnd" :aria-label="t.nextPage"
                  @click="page(1)">›</button>
        </div>

        <div v-if="outputs.length > 1" class="variants">
          <span class="vlabel">{{ t.variants }}</span>
          <button v-for="(o, i) in outputs" :key="o.filename" :class="{ on: i === picked }" @click="picked = i">
            <img v-if="kindOf(o) === 'image'" :src="o.url" :alt="o.filename" loading="lazy" />
            <span v-else class="ext">{{ extOf(o) }}</span>
          </button>
        </div>
      </template>
    </div>

    <div v-else-if="tab === 'status'" class="rbody narrow">
      <div v-if="!task" class="empty">{{ t.noData }}</div>
      <template v-else>
        <p class="statusline">
          <span class="chip" :class="task.state">{{ t.state[task.state] || task.state }}</span>
          <span v-if="task.error" class="err">{{ task.error }}</span>
        </p>
        <div class="bar"><i :style="{ width: task.progress + '%' }" /></div>
        <p class="pct">{{ task.progress }}%<span v-if="running" class="spin" /></p>
        <dl class="facts">
          <div><dt>{{ t.taskId }}</dt><dd>{{ task.ref }}</dd></div>
          <div><dt>{{ t.modelUsed }}</dt><dd>{{ task.model }}</dd></div>
          <div><dt>{{ t.created }}</dt><dd>{{ hhmm(task.created_at) }}</dd></div>
          <div><dt>{{ t.finished }}</dt><dd>{{ hhmm(task.finished_at) }}</dd></div>
          <div><dt>{{ t.elapsed }}</dt><dd>{{ task.seconds ? task.seconds.toFixed(1) + 's' : '—' }}</dd></div>
        </dl>
      </template>
    </div>

    <div v-else class="rbody narrow">
      <p v-if="!task" class="empty">{{ t.noData }}</p>
      <p v-else-if="!task.log?.length" class="empty">{{ t.noLog }}</p>
      <ul v-else class="log">
        <li v-for="(e, i) in task.log" :key="i" :class="{ last: i === task.log.length - 1 }">
          <time>{{ hhmm(e.ts) }}</time><span>{{ e.msg }}</span>
        </li>
      </ul>
    </div>
  </section>

  <Lightbox v-if="big && current" :title="nameOf(big)" :code="task.ref" :file="current" @close="big = null" />
</template>
