<script setup>
import { dismiss, toasts } from '../toast'
</script>

<template>
  <Teleport to="body">
    <TransitionGroup tag="div" name="toast" class="toasts" role="status" aria-live="polite">
      <div v-for="x in toasts" :key="x.id" class="toast" @click="dismiss(x.id)">{{ x.text }}</div>
    </TransitionGroup>
  </Teleport>
</template>
