<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { api } from '../api'
import { useI18n } from '../i18n'

const { t } = useI18n()
const health = ref(null)
const models = ref(null)
const engineErr = ref(false)

// /health is one cheap in-process counter, so it can poll often. /models asks the
// engine for four /object_info payloads, so it is read on demand only -- the numbers
// it reports (free VRAM, disk) carry that timestamp.
async function ping() {
  try { health.value = await api.health() } catch { health.value = null }
}
async function readEngine() {
  try { models.value = await api.models(); engineErr.value = false }
  catch { models.value = null; engineErr.value = true }
}
ping()
readEngine()
const timer = setInterval(ping, 5000)
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <section class="side-status">
    <h4>{{ t.engineTitle }}</h4>
    <p class="line">
      <i class="led" :class="{ off: !health?.ok }" />
      {{ t.health }} {{ health?.ok ? t.ok : t.degraded }}
    </p>
    <p v-if="health?.queued_ahead" class="line mono">{{ t.queuedAhead }} {{ health.queued_ahead }}</p>

    <template v-if="models">
      <p class="line mono">{{ models.engine.device }}</p>
      <p class="line mono">{{ t.version }} {{ models.engine.version }}</p>
      <p class="line mono">{{ t.vramFree }} {{ models.engine.vram_free_gb }}/{{ models.engine.vram_total_gb }} GB</p>
      <p class="line mono">{{ t.ramFree }} {{ models.engine.ram_free_gb }}/{{ models.engine.ram_total_gb }} GB</p>
      <h4 class="gap">{{ t.storage }}</h4>
      <div class="bar"><i :style="{ width: models.storage.pct + '%' }" /></div>
      <p class="line mono">
        {{ models.storage.used_gb }}/{{ models.storage.total_gb }} GB · {{ models.storage.pct }}% {{ t.usedOf }}
      </p>
    </template>
    <p v-else-if="engineErr" class="line mono">{{ t.engineTitle }} {{ t.degraded }}</p>

    <button class="ghost sm" @click="readEngine">{{ t.refresh }}</button>
  </section>
</template>
