<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../i18n'
import Lightbox from './Lightbox.vue'

const props = defineProps({ task: Object, runs: Array, templates: Array, filtered: Boolean })
const emit = defineEmits(['favorite', 'pick', 'useforvideo', 'deleted'])
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

// `i` is the slot's position in the row's own list, which keeps a deleted entry so an
// input binding made earlier still names the same file. The screen only shows what is
// left on disk, so everything here indexes the filtered list and hands `i` to the API.
function filesOf(t) {
  return (t?.outputs || []).map((o, i) => ({ ...o, i })).filter((o) => !o.deleted)
}
const outputs = computed(() => filesOf(props.task))
const picked = ref(0)
const tab = ref('preview')

// A run that was just submitted lands on 任务状态, which is the question being asked
// at that moment; a finished task opened from the list lands on its picture.
watch(() => props.task?.id, () => {
  picked.value = 0
  tab.value = ['queued', 'running'].includes(props.task?.state) ? 'status' : 'preview'
})
const current = computed(() => outputs.value[Math.min(picked.value, outputs.value.length - 1)] || null)
// A delete shrinks the list under the cursor; the index has to follow or the view would
// be handed a slot that is no longer there.
watch(() => outputs.value.length, (n) => { if (picked.value > n - 1) picked.value = Math.max(0, n - 1) })

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

const big = ref(null)   // the run whose picture is on screen full size
const hov = ref(null)   // the tile under the pointer; :hover was measured lying

async function choose(row) {
  // One click goes straight to the full view, opening on the first figure: the tile
  // already shows the picture, so the second click to enlarge it asked for nothing new.
  if (row.id !== props.task?.id) {
    await fetchOne(row.id)
    if (!full[row.id]) return
    emit('pick', full[row.id])
    await nextTick()      // the file list the view reads from is the row's own
  }
  if (!outputs.value.length) return
  picked.value = 0
  big.value = props.task
}

// The strip under a multi-figure run is a way in, not a switch: tapping the third
// thumbnail opens the full view on the third figure.
function openAt(i) {
  if (!outputs.value.length) return
  picked.value = i
  big.value = props.task
}

const bigTitle = computed(() => props.templates?.find((x) => x.id === big.value?.template)?.name
  || big.value?.template)

// A run whose figures are all gone leaves the line instead of holding a placeholder:
// the task row stays in 最近任务, but this line is for things that still exist. An
// unread row stays -- until it has been read there is no evidence either way.
const line = computed(() => (props.runs || []).map((r) => ({ id: r.id, run: r, task: full[r.id] || null }))
  .filter((x) => !x.task || filesOf(x.task).length))
const nameOf = (row) => props.templates?.find((x) => x.id === (row.task?.template || row.run.template))?.name
  || row.run.template
// The figure a tile stands for: the picked one for the selected run, the first left on
// disk for any other -- so the tools under the pointer act on what he is looking at.
const figureOf = (t) => filesOf(t)[0] || null
const figure = (row, t) => (row.id === props.task?.id ? current.value : figureOf(t))
function cover(row) { return figure(row, row.task) }

const favOf = (row) => (row.id === props.task?.id ? props.task : row.task)?.favorite || false

// A tile far down the line has no row yet: the rail only reads what nears view.
async function need(row) {
  if (row.id === props.task?.id) return props.task
  await fetchOne(row.id)
  return full[row.id] || null
}

async function toggleFav(row) {
  const t = await need(row)
  if (!t || !figure(row, t)) return
  await api.favorite(t.id, !favOf(row))
  const fresh = await api.task(t.id)
  full[t.id] = fresh
  if (t.id === props.task?.id) emit('favorite', fresh)
}

async function use(row, target) {
  const t = await need(row)
  const f = t ? figure(row, t) : null
  if (t && f) emit('useforvideo', { task: t, index: f.i, target: target.id })
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
// The line also loses a tile when its last figure is deleted, which changes whether it
// overflows at all -- so this watches the line, not the run list.
watch(() => [line.value.length, tab.value], () => nextTick(observe))
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
            <figure v-for="row in line" :key="row.id" class="shot"
                    :class="{ on: row.id === task?.id, hot: hov === row.id }"
                    :data-run="row.id" @pointerenter="hov = row.id" @pointerleave="hov = null"
                    @click="choose(row)">
              <div class="frame checker">
                <video v-if="cover(row) && kindOf(cover(row)) === 'video'" :src="cover(row).url"
                       preload="metadata" muted />
                <img v-else-if="cover(row) && kindOf(cover(row)) === 'image'" :src="cover(row).url"
                     :alt="cover(row).filename" loading="lazy" />
                <span v-else-if="cover(row)" class="ext">{{ extOf(cover(row)) }}</span>
                <span v-else class="none">{{ t.loading }}</span>
                <span v-if="cover(row) && kindOf(cover(row)) === 'video'" class="play">▶</span>

                <div v-if="cover(row)" class="corner">
                  <a class="iconbtn" :href="cover(row).url" :download="cover(row).filename" :title="t.download">⬇</a>
                  <button class="iconbtn" :class="{ fav: favOf(row) }" :title="favOf(row) ? t.favorited : t.favorite"
                          @click.stop="toggleFav(row)">
                    {{ favOf(row) ? '★' : '☆' }}
                  </button>
                  <button v-if="videoTargets.length" v-show="kindOf(cover(row)) === 'image'"
                          class="iconbtn" :title="`${t.useForVideo} · ${videoTargets[0].name}`"
                          @click.stop="use(row, videoTargets[0])">
                    ▷
                  </button>
                  <button v-if="hdImageTarget" v-show="kindOf(cover(row)) === 'image'"
                          class="iconbtn" :title="`${t.useForHD} · ${hdImageTarget.name}`"
                          @click.stop="use(row, hdImageTarget)">
                    ✦
                  </button>
                  <button v-if="editTarget" v-show="kindOf(cover(row)) === 'image'"
                          class="iconbtn" :title="`${t.useForEdit} · ${editTarget.name}`"
                          @click.stop="use(row, editTarget)">
                    ✎
                  </button>
                  <button v-if="hdVideoTarget" v-show="kindOf(cover(row)) === 'video'"
                          class="iconbtn" :title="`${t.useForHD} · ${hdVideoTarget.name}`"
                          @click.stop="use(row, hdVideoTarget)">
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
          <button v-for="(o, i) in outputs" :key="o.filename" :class="{ on: i === picked }" @click="openAt(i)">
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

  <Lightbox v-if="big && current" :title="bigTitle" :code="big.ref" :files="outputs" :task="big.id"
            v-model:index="picked" @deleted="emit('deleted', $event)" @close="big = null" />
</template>
