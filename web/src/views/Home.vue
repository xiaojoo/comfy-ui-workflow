<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '../api'
import { useI18n } from '../i18n'
import ParamPanel from '../components/ParamPanel.vue'
import PreviewRail from '../components/PreviewRail.vue'
import TaskTable from '../components/TaskTable.vue'

const { t } = useI18n()

const models = ref(null)
const templates = ref([])
const tasks = ref([])
const picked = ref(null)
const params = ref({})
const current = ref(null)
const query = ref('')
const cat = ref('all')
const busy = ref(false)
const err = ref('')

const THUMBS = { icon_flat: ['/thumbs/icon_flat.png'], icon_brand_tech: ['/thumbs/icon_tech.png'],
                 icon_batch: ['/thumbs/batch_bell.png', '/thumbs/batch_cloud.png',
                              '/thumbs/batch_arrow_up.png', '/thumbs/batch_trash.png'] }
const thumb = (id) => THUMBS[id] || []

const cats = computed(() => ['all', ...new Set(templates.value.map((x) => x.category))])
const shown = computed(() => templates.value.filter((x) => {
  if (cat.value !== 'all' && x.category !== (cat.value === 'enterprise_icon' ? 'enterprise_icon' : cat.value)) return false
  if (!query.value) return true
  const q = query.value.toLowerCase()
  return [x.name, x.name_en, x.desc, x.desc_en].join(' ').toLowerCase().includes(q)
}))

const step = computed(() => {
  if (!picked.value) return 1
  return busy.value || current.value ? 3 : 2
})

function choose(tpl) {
  picked.value = tpl
  params.value = JSON.parse(JSON.stringify(tpl.defaults))
  err.value = ''
}

async function refreshTasks() {
  tasks.value = (await api.tasks()).tasks
  if (!current.value && tasks.value.length) adopt(tasks.value[0])
}

// On first load the newest task is shown, and the form is set to match it -- a panel
// offering "gear" beside a preview of a shield reads as two unrelated tools.
function adopt(row) {
  return api.task(row.id).then((f) => {
    const tpl = templates.value.find((x) => x.id === f.template)
    if (tpl) picked.value = tpl
    params.value = { ...f.params }
    current.value = f
    return f
  })
}

async function submit() {
  busy.value = true
  err.value = ''
  try {
    const r = await api.createTask({ template: picked.value.id, prompt: params.value.prompt,
                                     params: params.value })
    current.value = await api.task(r.task_id)
    await refreshTasks()
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

async function viewTask(row) {
  current.value = await api.task(row.id)
  const tpl = templates.value.find((x) => x.id === row.template)
  if (tpl) picked.value = tpl
}

const storage = computed(() => models.value?.storage || null)

let timer = null
async function boot() {
  try {
    const [m, tp] = await Promise.all([api.models(), api.templates()])
    models.value = m
    templates.value = tp.templates
    if (tp.templates.length) choose(tp.templates[0])
    await refreshTasks()
  } catch (e) {
    err.value = e.message
  }
  timer = setInterval(async () => {
    try {
      await refreshTasks()
      if (current.value && ['queued', 'running'].includes(current.value.state)) {
        current.value = await api.task(current.value.id)
      }
    } catch { /* engine restarting; the next tick recovers */ }
  }, 1500)
}
boot()
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="page">
    <section class="hero">
      <div>
        <h1>{{ t.brand }}</h1>
        <p>{{ t.tagline }}</p>
        <ul class="feats">
          <li v-for="(f, i) in t.features" :key="i"><b>{{ f[0] }}</b><span>{{ f[1] }}</span></li>
        </ul>
      </div>
      <div class="hero-art"><img src="/thumbs/icon_flat.png" alt="" /></div>
    </section>

    <nav class="steps">
      <span v-for="(s, i) in t.wizard" :key="i" :class="{ on: step === i + 1 }"><b>{{ i + 1 }}</b>{{ s }}</span>
    </nav>

    <div class="cols">
      <div class="col-main">
        <section class="card">
          <h2>{{ t.nav.workflows }}
            <input v-model="query" class="mini" :placeholder="t.search" />
          </h2>
          <div class="chips">
            <button v-for="c in cats" :key="c" class="ghost sm" :class="{ on: cat === c }" @click="cat = c">
              {{ c === 'all' ? t.categoryAll : t.categories[c] || c }}
            </button>
          </div>
          <div class="cards">
            <article v-for="x in shown" :key="x.id" class="tpl" :class="{ on: picked?.id === x.id }"
                     @click="choose(x)">
              <div class="shots" :class="{ multi: thumb(x.id).length > 1 }">
                <img v-for="u in thumb(x.id)" :key="u" :src="u" :alt="x.name" />
              </div>
              <h3>{{ x.name }}<i v-if="picked?.id === x.id" class="tick">✓</i></h3>
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
          <p v-if="err" class="drift">{{ err }}</p>
        </section>

        <TaskTable :tasks="tasks" @pick="viewTask" />
      </div>

      <div class="col-side">
        <ParamPanel v-if="picked" :template="picked" :params="params" :models="models?.catalog" :busy="busy"
                    @submit="submit" />
        <section v-else class="card"><div class="empty">{{ t.selectBatch }}</div></section>
      </div>

      <PreviewRail :task="current" @favorite="favorite" />
    </div>

    <footer v-if="storage" class="foot">
      <div class="stor">
        <h4>{{ t.storage }}</h4>
        <div class="bar"><i :style="{ width: storage.pct + '%' }" /></div>
        <p>{{ storage.used_gb }} GB / {{ storage.total_gb }} GB · {{ storage.pct }}% {{ t.usedOf }}</p>
      </div>
      <div v-if="models" class="eng">
        <h4>{{ t.engineTitle }}</h4>
        <p>{{ models.engine.device }} · {{ t.version }} {{ models.engine.version }}</p>
        <p>{{ t.vramFree }} {{ models.engine.vram_free_gb }}/{{ models.engine.vram_total_gb }} GB ·
           {{ t.ramFree }} {{ models.engine.ram_free_gb }}/{{ models.engine.ram_total_gb }} GB</p>
      </div>
    </footer>
  </div>
</template>
