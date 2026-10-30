<script setup lang="ts">
import { computed, ref } from 'vue'

import { useQueues } from '@/entities/call-data'
import { useSessionStore } from '@/entities/session'
import { formatHours, useEmployees, type Employee } from '@/entities/scheduling'
import { EmployeeForm } from '@/features/people/employee'
import { AnonymisePanel, RetentionPanel } from '@/features/people/erasure'
import { ImportEmployeesPanel } from '@/features/people/import-employees'
import { MapLoginsPanel } from '@/features/people/map-logins'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'employees')
// Cosmetic: the API refuses changes from any other role.
const canChange = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))
const isAdmin = computed(() => session.user?.role === 'admin')

const employees = useEmployees()
const queues = useQueues()

// "new" shows the add form; an employee shows the change form for them; null shows neither.
const editing = ref<Employee | 'new' | null>(null)
const importing = ref(false)
const anonymising = ref<Employee | null>(null)
const ERASED = 'ERASED-'
function review(employeeId: number): void {
  anonymising.value = (employees.data.value ?? []).find((e) => e.id === employeeId) ?? null
}
// ---- the directory: who, filtered by what they are and where they work ----
const search = ref('')
const contract = ref<string | null>(null)
const queue = ref<string | null>(null)
const everyone = computed(() => employees.data.value ?? [])
const count = (test: (e: Employee) => boolean): number => everyone.value.filter(test).length
const queueNames = computed(() =>
  [...new Set(everyone.value.flatMap((e) => e.skills.map((k) => k.queue)))].sort(),
)
const shown = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return everyone.value.filter(
    (e) =>
      (contract.value === null || e.contractType === contract.value) &&
      (queue.value === null || e.skills.some((k) => k.queue === queue.value)) &&
      (needle === '' ||
        e.name.toLowerCase().includes(needle) ||
        e.empNo.toLowerCase().includes(needle)),
  )
})
const hoursTotal = computed(() => everyone.value.reduce((sum, e) => sum + e.weeklyHours, 0))
const initials = (name: string): string =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join('')
const AVATAR = ['bg-brand-soft', 'bg-ok-soft', 'bg-warn-soft', 'bg-danger-soft'] as const
const CONTRACT: Record<string, string> = { permanent: 'Permanent', seasonal: 'Seasonal' }
const MODE: Record<string, string> = { office: 'Office', remote: 'Remote', hybrid: 'Hybrid' }
</script>

<template>
  <PageHeader eyebrow="People" :title="screen?.label ?? 'Employees'" :subtitle="screen?.subtitle">
    <template v-if="canChange" #actions>
      <AppButton v-if="editing === null" @click="editing = 'new'">Add employee</AppButton>
      <AppButton variant="secondary" :aria-pressed="importing" @click="importing = !importing">
        Import employees
      </AppButton>
    </template>
  </PageHeader>

  <section class="space-y-6" aria-live="polite">
    <ImportEmployeesPanel v-if="importing && canChange" />
    <AnonymisePanel
      v-if="isAdmin && anonymising"
      :key="anonymising.id"
      :employee-id="anonymising.id"
      :employee-label="anonymising.name"
      @done="anonymising = null"
      @cancel="anonymising = null"
    />

    <EmployeeForm
      v-if="editing !== null && canChange"
      :key="editing === 'new' ? 'new' : editing.id"
      :employee="editing === 'new' ? null : editing"
      :queues="queues.data.value ?? []"
      :managers="(employees.data.value ?? []).filter((e) => e.canManage)"
      @saved="editing = null"
      @cancel="editing = null"
    />

    <p v-if="employees.isPending.value" class="text-sm text-ink-muted">Loading…</p>
    <NoticeBox v-else-if="employees.isError.value" tone="danger">
      Could not load the employees. {{ problemMessage(employees.error.value) }}
    </NoticeBox>
    <NoticeBox v-else-if="(employees.data.value ?? []).length === 0">
      There are no employees yet.
      <template v-if="canChange">Add the first one to start building a roster.</template>
    </NoticeBox>

    <template v-else>
      <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Headcount">
        <StatTile label="Headcount" :value="everyone.length" tint="brand" data-testid="stat-people">
          {{ count((e) => e.contractType === 'permanent') }} permanent ·
          {{ count((e) => e.contractType === 'seasonal') }} seasonal
        </StatTile>
        <StatTile label="Contract hours" :value="hoursTotal" tint="ok" data-testid="stat-hours">
          a week, all together
        </StatTile>
        <StatTile
          label="Remote or hybrid"
          :value="count((e) => e.workMode !== 'office')"
          tint="warn"
          data-testid="stat-remote"
        >
          {{ count((e) => e.workMode === 'office') }} in the office
        </StatTile>
        <StatTile
          label="Without a login mapped"
          :value="count((e) => e.agentLogins.length === 0)"
          tint="danger"
          data-testid="stat-unmapped"
        >
          no ACD login tied to them
        </StatTile>
      </ul>

      <div class="flex flex-wrap items-center gap-2" role="group" aria-label="Filter the directory">
        <label class="relative block w-full sm:w-64">
          <span class="sr-only">Search by name or number</span>
          <input
            v-model="search"
            type="search"
            placeholder="Search by name or number"
            class="min-h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm text-ink"
          />
        </label>
        <button
          type="button"
          class="press rounded-full px-3 py-1.5 text-sm"
          :class="
            contract === null && queue === null
              ? 'bg-brand text-brand-contrast'
              : 'bg-surface text-ink'
          "
          :aria-pressed="contract === null && queue === null"
          @click="((contract = null), (queue = null))"
        >
          All <span class="opacity-70">{{ everyone.length }}</span>
        </button>
        <button
          v-for="c in ['permanent', 'seasonal']"
          :key="c"
          type="button"
          class="press rounded-full px-3 py-1.5 text-sm"
          :class="contract === c ? 'bg-brand text-brand-contrast' : 'bg-surface text-ink'"
          :aria-pressed="contract === c"
          @click="contract = contract === c ? null : c"
        >
          {{ CONTRACT[c] }}
          <span class="opacity-70">{{ count((e) => e.contractType === c) }}</span>
        </button>
        <button
          v-for="q in queueNames"
          :key="q"
          type="button"
          class="press rounded-full px-3 py-1.5 text-sm"
          :class="queue === q ? 'bg-brand text-brand-contrast' : 'bg-surface text-ink'"
          :aria-pressed="queue === q"
          @click="queue = queue === q ? null : q"
        >
          {{ q }}
          <span class="opacity-70">{{ count((e) => e.skills.some((k) => k.queue === q)) }}</span>
        </button>
      </div>

      <NoticeBox v-if="shown.length === 0" data-testid="no-match"> Nobody matches that. </NoticeBox>
      <ul v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Employees">
        <li
          v-for="e in shown"
          :key="e.id"
          class="flex flex-col rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-card)]"
          :data-testid="`employee-${e.empNo}`"
        >
          <div class="flex items-start gap-3">
            <span
              class="grid size-11 shrink-0 place-items-center rounded-full text-sm font-semibold text-ink"
              :class="AVATAR[e.id % AVATAR.length]"
              aria-hidden="true"
            >
              {{ initials(e.name) }}
            </span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-semibold text-ink">{{ e.name }}</p>
              <p class="truncate text-xs tabular-nums text-ink-muted">{{ e.empNo }}</p>
            </div>
            <span
              class="shrink-0 rounded-full bg-surface-muted px-2 py-0.5 text-[11px] font-semibold text-ink"
            >
              {{ CONTRACT[e.contractType] ?? e.contractType }}
            </span>
          </div>

          <dl class="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt class="text-ink-muted">Weekly hours</dt>
            <dd class="text-right tabular-nums text-ink">
              {{ formatHours(e.weeklyHours * 60) }}
              <span
                v-if="e.weeklyHoursIsDefault"
                class="ml-1 rounded-full bg-warn-soft px-1.5 py-0.5 text-[10px] font-semibold text-warn"
                title="Nobody has entered this person's hours; this is the default"
                >Default</span
              >
            </dd>
            <dt class="text-ink-muted">Works</dt>
            <dd class="text-right text-ink">{{ MODE[e.workMode] ?? e.workMode }}</dd>
            <dt class="text-ink-muted">Manager</dt>
            <dd class="truncate text-right text-ink">{{ e.manager ?? '—' }}</dd>
            <dt class="text-ink-muted">ACD logins</dt>
            <dd class="truncate text-right text-ink">{{ e.agentLogins.join(', ') || '—' }}</dd>
          </dl>

          <ul class="mt-3 flex flex-wrap gap-1.5" aria-label="Queues">
            <li
              v-for="k in e.skills"
              :key="k.queue"
              class="rounded-full bg-brand-soft px-2 py-0.5 text-[11px] font-medium text-brand-ink"
            >
              {{ k.queue }} L{{ k.level }}
            </li>
            <li v-if="e.skills.length === 0" class="text-xs text-ink-muted">No queues</li>
          </ul>

          <div v-if="canChange" class="mt-auto flex flex-wrap gap-x-3 gap-y-1 pt-3 text-sm">
            <button
              type="button"
              class="font-medium text-brand-ink underline"
              :aria-label="`Change ${e.name}`"
              @click="editing = e"
            >
              Change
            </button>
            <a
              v-if="isAdmin"
              :href="`/api/v1/people/employees/${e.id}/data-export`"
              download
              class="font-medium text-brand-ink underline"
              :aria-label="`Export the data held about ${e.name}`"
            >
              Export data
            </a>
            <button
              v-if="isAdmin && !e.empNo.startsWith(ERASED)"
              type="button"
              class="font-medium text-danger underline"
              :aria-label="`Anonymise ${e.name}`"
              @click="anonymising = e"
            >
              Anonymise
            </button>
          </div>
        </li>
      </ul>

      <details
        v-if="canChange"
        class="rounded-2xl border border-line bg-surface p-4"
        data-testid="logins-section"
      >
        <summary class="cursor-pointer text-base font-semibold text-ink">
          ACD logins to link
        </summary>
        <div class="mt-3"><MapLoginsPanel :employees="everyone" /></div>
      </details>
      <details v-if="isAdmin" class="rounded-2xl border border-line bg-surface p-4">
        <summary class="cursor-pointer text-base font-semibold text-ink">Retention</summary>
        <div class="mt-3"><RetentionPanel @review="review" /></div>
      </details>
    </template>
  </section>
</template>
