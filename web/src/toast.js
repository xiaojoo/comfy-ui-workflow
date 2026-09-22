import { reactive } from 'vue'

// One list, one renderer, mounted in App.vue. The place that has the news is often the
// place about to disappear -- the full-size view closes itself when its last figure is
// removed -- so a toast cannot live inside the component that raises it.
const toasts = reactive([])
let seq = 0

export function dismiss(id) {
  const i = toasts.findIndex((x) => x.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

export function notify(text, ms = 3600) {
  const id = ++seq
  toasts.push({ id, text })
  setTimeout(() => dismiss(id), ms)
  return id
}

export { toasts }
