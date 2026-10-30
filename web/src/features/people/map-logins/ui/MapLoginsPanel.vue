<script setup lang="ts">
import { computed, ref } from 'vue'

import { useUnmappedLogins } from '@/entities/scheduling'
import type { Employee } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useMapLogins } from '../model/useMapLogins'

const props = defineProps<{ employees: ReadonlyArray<Employee> }>()

const unmapped = useUnmappedLogins()
const map = useMapLogins()
const choice = ref<Record<string, string>>({})
const byId = computed(() => new Map(props.employees.map((e) => [e.id, e])))

function assign(login: string): void {
  const id = Number(choice.value[login])
  const person = byId.value.get(id)
  if (!person) return
  // Several logins can be one person: add this one to the ones they already have.
  map.mutate({ employeeId: id, logins: [...person.agentLogins, login] })
}
</script>

<template>
  <section
    v-if="(unmapped.data.value ?? []).length > 0"
    class="space-y-3"
    aria-labelledby="map-title"
  >
    <h2 id="map-title" class="text-base font-semibold text-ink">ACD logins nobody owns yet</h2>
    <ul class="space-y-2" aria-label="Unmapped ACD logins">
      <li
        v-for="u in unmapped.data.value"
        :key="u.login"
        class="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface px-4 py-2"
        :data-testid="`unmapped-${u.login}`"
      >
        <span class="min-w-40 text-sm text-ink">
          <span class="font-medium">{{ u.login }}</span>
          <span class="text-ink-muted">
            · {{ u.calls }} {{ u.calls === 1 ? 'call' : 'calls' }}</span
          >
        </span>
        <select
          v-model="choice[u.login]"
          class="rounded-md border border-line bg-surface px-1 py-1 text-sm text-ink"
          :aria-label="`Who is ${u.login}`"
        >
          <option value="">Choose a person</option>
          <option v-for="e in employees" :key="e.id" :value="String(e.id)">
            {{ e.name }} ({{ e.empNo }})
          </option>
        </select>
        <button
          type="button"
          class="text-sm font-medium text-brand-ink underline disabled:opacity-60"
          :disabled="!choice[u.login]"
          :aria-label="`Tie ${u.login} to the chosen person`"
          @click="assign(u.login)"
        >
          Tie
        </button>
      </li>
    </ul>
    <NoticeBox v-if="map.isError.value" tone="danger" data-testid="map-error">
      {{ problemMessage(map.error.value) }}
    </NoticeBox>
  </section>
</template>
