<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '../api'
import { useI18n } from '../i18n'
import ParamPanel from '../components/ParamPanel.vue'
import ResultTabs from '../components/ResultTabs.vue'

const { t } = useI18n()

const models = ref(null)
const templates = ref([])
const picked = ref(null)
const params = ref({})
const current = ref(null)
const runs = ref([])
const query = ref('')
const cat = ref('all')
const busy = ref(false)
const drawer = ref(false)
const err = ref('')
const pageErr = ref('')

const THUMBS = { icon_flat: ['/thumbs/icon_flat.png'], icon_brand_tech: ['/thumbs/icon_tech.png'],
                 icon_batch: ['/thumbs/batch_bell.png', '/thumbs/batch_cloud.png',
                              '/thumbs/batch_arrow_up.png', '/thumbs/batch_trash.png'] }
const thumb = (id) => THUMBS[id] || []

const cats = computed(() => ['all', ...new Set(templates.value.map((x) => x.category))])
const shown = computed(() => templates.value.filter((x) => {
  if (cat.value !== 'all' && x.category !== cat.value) return false
  if (!query.value) return true
  const q = query.value.toLowerCase()
  return [x.name, x.name_en, x.desc, x.desc_en].join(' ').toLowerCase().includes(q)
}))

// Clicking a card filters the result line to that workflow and configures it; clicking
// the same card again lifts both. The filter is not the selection: picking a run in the
// line changes the form without hiding the other workflows.
const onlyTpl = ref('')
const lineRuns = computed(() => (onlyTpl.value ? runs.value.filter((x) => x.template === onlyTpl.value) : runs.value))

function choose(tpl) {
  if (onlyTpl.value === tpl.id && drawer.value) {
    // Lifting the selection clears the inspected run too: 任务状态 and 执行日志 report on
    // the selected workflow, so with nothing selected they show no data rather than the
    // last run some other workflow produced.
    onlyTpl.value = ''
    drawer.value = false
    current.value = null
    return
  }
  picked.value = tpl
  params.value = JSON.parse(JSON.stringify(tpl.defaults))
  drawer.value = true
  onlyTpl.value = tpl.id
  err.value = ''
  const first = runs.value.find((x) => x.template === tpl.id)
  if (first) show(first.id)
  else current.value = null
}

// The preview line is every run that produced something, newest first. The list rows
// carry no outputs on purpose -- ResultTabs reads a run's files only once its tile is
// about to come into view, so the page asks for what it can show.
async function loadRuns() {
  runs.value = (await api.tasks(200)).tasks.filter((x) => x.state === 'done')
}

// The form follows the preview: a panel offering "gear" beside a preview of a shield
// reads as two unrelated tools.
function adopt(f) {
  const tpl = templates.value.find((x) => x.id === f.template)
  if (tpl) { picked.value = tpl; params.value = { ...f.params } }
  current.value = f
}

async function show(id) {
  adopt(await api.task(id))
}

async function submit() {
  busy.value = true
  err.value = ''
  try {
    const r = await api.createTask({ template: picked.value.id, prompt: params.value.prompt,
                                     params: params.value })
    current.value = await api.task(r.task_id)
  } catch (e) {
    err.value = `${e.status ?? ''} ${e.message}`
  } finally {
    busy.value = false
  }
}

async function favorite(v) {
  await api.favorite(current.value.id, v)
  current.value = await api.task(current.value.id)
}

let timer = null
async function boot() {
  try {
    const [m, tp] = await Promise.all([api.models(), api.templates()])
    models.value = m
    templates.value = tp.templates
    await loadRuns()
    // Nothing is inspected until he picks: clicking a tile in the preview line is the
    // only way in, so the page never opens a run it was not asked to show.
  } catch (e) {
    pageErr.value = e.message
  }
  timer = setInterval(async () => {
    try {
      if (current.value && ['queued', 'running'].includes(current.value.state)) {
        current.value = await api.task(current.value.id)
        if (!['queued', 'running'].includes(current.value.state)) await loadRuns()
      }
    } catch { /* engine restarting; the next tick recovers */ }
  }, 1500)
}
boot()
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="page">
    <header class="pagehead">
      <h1>{{ t.nav.workflows }}</h1>
      <p>{{ t.wfSubtitle }}</p>
    </header>
    <p v-if="pageErr" class="drift">{{ pageErr }}</p>

    <div class="split" :class="{ open: drawer && picked }">
      <div class="stack">
        <section class="card">
          <div class="picker">
            <div class="chips">
              <button v-for="c in cats" :key="c" class="ghost sm" :class="{ on: cat === c }" @click="cat = c">
                {{ c === 'all' ? t.categoryAll : t.categories[c] || c }}
              </button>
            </div>
            <input v-model="query" class="mini" :placeholder="t.search" />
          </div>
          <div class="cards">
            <article v-for="x in shown" :key="x.id" class="tpl" :class="{ on: drawer && picked?.id === x.id }"
                     @click="choose(x)">
              <div class="shots" :class="{ multi: thumb(x.id).length > 1 }">
                <img v-for="u in thumb(x.id)" :key="u" :src="u" :alt="x.name" />
              </div>
              <h3><span class="nm">{{ x.name }}</span><i v-if="drawer && picked?.id === x.id" class="tick">✓</i></h3>
              <p>{{ x.desc }}</p>
              <div class="tags">
                <span class="chip">{{ x.model }}</span>
                <span class="chip">{{ x.spec }}</span>
                <span class="chip" :class="x.verified ? 'ok-text' : 'running'">
                  {{ x.verified ? t.verified : t.unverified }}
                </span>
              </div>
            </article>
          </div>
        </section>

        <ResultTabs :task="current" :runs="lineRuns" :templates="templates" :filtered="!!onlyTpl"
                    @favorite="favorite" @pick="adopt" />
      </div>

      <ParamPanel v-if="drawer && picked" :template="picked" :params="params" :models="models?.catalog"
                  :busy="busy" :err="err" @submit="submit" @close="drawer = false" />
    </div>
  </div>
</template>
