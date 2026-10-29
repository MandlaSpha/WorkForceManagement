<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { formatHours, useShifts } from '@/entities/scheduling'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SettingsCard from '@/shared/ui/SettingsCard.vue'
import SettingsRow from '@/shared/ui/SettingsRow.vue'
import TextField from '@/shared/ui/TextField.vue'

import { PAGE_SIZE, type Sort, type SortKey, visibleShifts } from '../model/table'
import { useShiftMutations } from '../model/useShiftMutations'

const shifts = useShifts()
const { create, remove } = useShiftMutations()

const code = ref('')
const start = ref('09:00')
const end = ref('17:30')
const paid = ref('480')

const search = ref('')
const sort = ref<Sort>({ key: 'startTime', dir: 'asc' })
const shown = ref(PAGE_SIZE)
/** The shift whose delete is waiting for a second click. */
const confirming = ref<number | null>(null)

const rows = computed(() => visibleShifts(shifts.data.value ?? [], search.value, sort.value))
const page = computed(() => rows.value.slice(0, shown.value))
watch(search, () => (shown.value = PAGE_SIZE))

const COLUMNS: ReadonlyArray<{ key: SortKey; label: string }> = [
  { key: 'code', label: 'Code' },
  { key: 'startTime', label: 'Start' },
  { key: 'endTime', label: 'End' },
  { key: 'paidMinutes', label: 'Paid hours' },
]

function sortBy(key: SortKey): void {
  sort.value =
    sort.value.key === key
      ? { key, dir: sort.value.dir === 'asc' ? 'desc' : 'asc' }
      : { key, dir: 'asc' }
}

function ariaSort(key: SortKey): 'ascending' | 'descending' | 'none' {
  if (sort.value.key !== key) return 'none'
  return sort.value.dir === 'asc' ? 'ascending' : 'descending'
}

function askToDelete(id: number): void {
  remove.reset()
  confirming.value = id
}

function confirmDelete(id: number): void {
  remove.mutate(id, { onSettled: () => (confirming.value = null) })
}

function add(): void {
  create.mutate(
    {
      code: code.value.trim(),
      startTime: start.value,
      endTime: end.value,
      paidMinutes: Number(paid.value),
    },
    { onSuccess: () => (code.value = '') },
  )
}
</script>

<template>
  <div class="space-y-6">
    <SettingsCard
      title="Shift templates"
      description="A shift that ends at or before its start runs overnight. Once people are rostered on a shift its times cannot change, and it cannot be deleted."
    >
      <div class="space-y-4 py-4">
        <div v-if="shifts.isPending.value" class="space-y-2" aria-busy="true" aria-label="Loading">
          <div v-for="n in 4" :key="n" class="skeleton h-10" />
        </div>
        <NoticeBox v-else-if="shifts.isError.value" tone="danger">
          Could not load the shifts. {{ problemMessage(shifts.error.value) }}
        </NoticeBox>
        <NoticeBox v-else-if="(shifts.data.value ?? []).length === 0">
          No shifts yet. Add one below.
        </NoticeBox>
        <template v-else>
          <div class="max-w-xs">
            <TextField v-model="search" label="Search shifts" />
          </div>
          <p v-if="rows.length === 0" class="py-2 text-sm text-ink-muted" role="status">
            No shift matches "{{ search }}".
          </p>
          <div v-else class="overflow-x-auto">
            <table class="w-full min-w-[30rem] text-left text-sm" aria-label="Shifts">
              <thead>
                <tr class="border-b border-line text-xs text-ink-muted">
                  <th
                    v-for="c in COLUMNS"
                    :key="c.key"
                    scope="col"
                    class="py-2 pr-3 font-medium"
                    :aria-sort="ariaSort(c.key)"
                  >
                    <button
                      type="button"
                      class="press inline-flex items-center gap-1 rounded-md hover:text-ink"
                      @click="sortBy(c.key)"
                    >
                      {{ c.label }}
                      <span aria-hidden="true">{{
                        sort.key === c.key ? (sort.dir === 'asc' ? '↑' : '↓') : ''
                      }}</span>
                    </button>
                  </th>
                  <th scope="col" class="py-2 text-right font-medium">
                    <span class="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line">
                <tr v-for="shift in page" :key="shift.id">
                  <th scope="row" class="py-2.5 pr-3 font-semibold text-ink">{{ shift.code }}</th>
                  <td class="pr-3 tabular-nums">{{ shift.startTime }}</td>
                  <td class="pr-3 tabular-nums">
                    {{ shift.endTime }}
                    <span v-if="shift.overnight" class="text-xs text-ink-muted">(overnight)</span>
                  </td>
                  <td class="pr-3 tabular-nums">{{ formatHours(shift.paidMinutes) }} paid</td>
                  <td class="py-1.5 text-right">
                    <span v-if="confirming === shift.id" class="inline-flex items-center gap-2">
                      <span class="text-xs text-ink-muted">Delete {{ shift.code }}?</span>
                      <AppButton
                        variant="secondary"
                        :loading="remove.isPending.value"
                        @click="confirmDelete(shift.id)"
                      >
                        Yes, delete
                      </AppButton>
                      <AppButton variant="ghost" @click="confirming = null">Cancel</AppButton>
                    </span>
                    <button
                      v-else
                      type="button"
                      class="press inline-flex size-10 items-center justify-center rounded-lg text-ink-muted hover:bg-danger-soft hover:text-danger"
                      :aria-label="`Delete shift ${shift.code}`"
                      @click="askToDelete(shift.id)"
                    >
                      <svg
                        viewBox="0 0 24 24"
                        class="size-5"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.8"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12h10l1-12M9 7V4h6v3" />
                      </svg>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="rows.length > 0" class="flex flex-wrap items-center justify-between gap-2">
            <p class="text-xs text-ink-muted" role="status">
              Showing {{ page.length }} of {{ rows.length }}
            </p>
            <AppButton v-if="rows.length > shown" variant="secondary" @click="shown += PAGE_SIZE">
              Show more ({{ rows.length - shown }} left)
            </AppButton>
          </div>
        </template>
        <NoticeBox v-if="remove.isError.value" tone="danger" data-testid="shift-delete-error">
          <p class="font-medium">The shift was not deleted.</p>
          <p>{{ problemMessage(remove.error.value) }}</p>
        </NoticeBox>
      </div>
    </SettingsCard>

    <form aria-label="Add a shift" @submit.prevent="add">
      <SettingsCard
        title="Add a shift"
        description="Times are on the hour or half-hour. Paid minutes are the clock length less unpaid breaks."
      >
        <SettingsRow label="Code" helper="A short name people recognise, such as D1.">
          <TextField v-model="code" label="Code" hide-label />
        </SettingsRow>
        <SettingsRow label="Starts" helper="When the shift begins.">
          <TextField v-model="start" type="time" label="Start" hide-label :step="1800" />
        </SettingsRow>
        <SettingsRow label="Ends" helper="At or before the start means it runs overnight.">
          <TextField v-model="end" type="time" label="End" hide-label :step="1800" />
        </SettingsRow>
        <SettingsRow label="Paid minutes" helper="What the person is paid for.">
          <TextField v-model="paid" type="number" label="Paid minutes" hide-label :min="1" />
        </SettingsRow>
        <template #footer>
          <div class="flex flex-wrap items-center justify-between gap-3">
            <NoticeBox v-if="create.isError.value" tone="danger" data-testid="shift-error">
              <p class="font-medium">The shift was not added.</p>
              <p>{{ problemMessage(create.error.value) }}</p>
            </NoticeBox>
            <span v-else class="text-sm text-ink-muted">
              It is available as soon as it is added.
            </span>
            <AppButton
              type="submit"
              :loading="create.isPending.value"
              :disabled="code.trim() === ''"
            >
              Add shift
            </AppButton>
          </div>
        </template>
      </SettingsCard>
    </form>
  </div>
</template>
