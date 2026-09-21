<script setup>
import { useI18n } from '../i18n'

defineProps({ navKey: String })
const { t } = useI18n()
</script>

<template>
  <section class="card placeholder">
    <h2>{{ t.nav[navKey] }}</h2>
    <p class="big">{{ t.navTodo }}</p>
    <p class="hint">{{ t.navTodoBody }}</p>
    <RouterLink class="back" to="/">{{ t.nav.workflows }}</RouterLink>
  </section>
</template>
