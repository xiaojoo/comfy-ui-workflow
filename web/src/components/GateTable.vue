<script setup>
import { useI18n } from '../i18n'

const props = defineProps({ gate: Object, selected: Number })
const emit = defineEmits(['approve', 'select'])
const { t, col } = useI18n()

function limitText(colKey) {
  const spec = props.gate.column_budget?.[colKey]
  if (!spec) return t.value.limitAdvisory
  if (spec.bound === 'band') return `${t.value.limitBand} ${spec.target}±${spec.dev}`
  return `${spec.bound === 'max' ? t.value.limitMax : t.value.limitMin}${spec.limit}`
}
</script>

<template>
  <div>
    <!-- Colour comes from row.checks, which the gate computes from the same limits
         that produce the verdict. Nothing here re-derives a comparison. -->
    <div class="scroller">
      <table class="gate">
      <thead>
        <tr>
          <th class="sticky-left">{{ t.th.asset }}</th>
          <th v-for="c in gate.columns" :key="c" class="metric">
            <div class="label">{{ col[c] || c }}</div>
            <div class="limit">{{ limitText(c) }}</div>
          </th>
          <th>{{ t.th.fails }}</th>
          <th>{{ t.th.verdict }}</th>
          <th>{{ t.th.approved }}</th>
          <th class="actions-col">{{ t.th.actions }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in gate.rows" :key="row.id" :class="{ active: row.id === selected }">
          <th class="sticky-left name" @click="emit('select', row)">{{ row.name }}</th>
          <td v-for="c in gate.columns" :key="c"
              :class="['metric', row.checks[c] === null ? 'advisory' : row.checks[c] ? 'ok' : 'bad']"
          >{{ row[c] === null || row[c] === undefined ? '—' : row[c] }}</td>
          <td class="fails" :title="row.fails?.join(' · ')">
            <template v-if="row.fails?.length">
              <code>{{ row.fails[0] }}</code>
              <span v-if="row.fails.length > 1" class="more">+{{ row.fails.length - 1 }}</span>
            </template>
            <span v-else class="muted">{{ t.errorNone }}</span>
          </td>
          <td><span class="chip" :class="row.verdict.toLowerCase()">{{ t.verdict[row.verdict] }}</span></td>
          <td><span class="chip" :class="'ap-' + row.approval">{{ t.approval[row.approval] }}</span></td>
          <td class="actions">
            <button
              :disabled="row.verdict !== 'PASS'"
              :title="row.verdict !== 'PASS' ? t.approveBlocked : ''"
              @click="emit('approve', { id: row.id, approve: true })"
            >{{ t.approve }}</button>
            <button class="ghost" @click="emit('approve', { id: row.id, approve: false })">{{ t.reject }}</button>
          </td>
        </tr>
      </tbody>
      </table>
    </div>
    <p class="note">{{ t.colsNote }}</p>
  </div>
</template>
