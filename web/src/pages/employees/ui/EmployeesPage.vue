<script setup lang="ts">
import { computed, ref } from 'vue'

import { useQueues } from '@/entities/call-data'
import { useSessionStore } from '@/entities/session'
import { formatHours, useEmployees, type Employee } from '@/entities/scheduling'
import { EmployeeForm } from '@/features/people/employee'
import { ImportEmployeesPanel } from '@/features/people/import-employees'
import { MapLoginsPanel } from '@/features/people/map-logins'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'employees')
// Cosmetic: the API refuses changes from any other role.
const canChange = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

const employees = useEmployees()
const queues = useQueues()

// "new" shows the add form; an employee shows the change form for them; null shows neither.
const editing = ref<Employee | 'new' | null>(null)
const importing = ref(false)
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
    <MapLoginsPanel v-if="canChange" :employees="employees.data.value ?? []" />

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

    <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
      <table class="w-full min-w-[44rem] text-left text-sm">
        <caption class="px-4 py-3 text-left text-sm font-semibold text-ink">
          Employees
        </caption>
        <thead class="border-y border-line bg-surface-muted text-xs text-ink-muted">
          <tr>
            <th scope="col" class="px-4 py-2 font-medium">Name</th>
            <th scope="col" class="px-3 py-2 font-medium">Number</th>
            <th scope="col" class="px-3 py-2 font-medium">Contract</th>
            <th scope="col" class="px-3 py-2 font-medium">Weekly hours</th>
            <th scope="col" class="px-3 py-2 font-medium">Works</th>
            <th scope="col" class="px-3 py-2 font-medium">Queues</th>
            <th scope="col" class="px-3 py-2 font-medium">Manager</th>
            <th scope="col" class="px-3 py-2 font-medium">ACD logins</th>
            <th scope="col" class="px-4 py-2 text-right font-medium">
              <span class="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in employees.data.value" :key="e.id" class="border-b border-line">
            <th scope="row" class="px-4 py-2 font-medium text-ink">{{ e.name }}</th>
            <td class="px-3 py-2 tabular-nums">{{ e.empNo }}</td>
            <td class="px-3 py-2">{{ CONTRACT[e.contractType] ?? e.contractType }}</td>
            <td class="px-3 py-2 tabular-nums">
              {{ formatHours(e.weeklyHours * 60) }}
              <span
                v-if="e.weeklyHoursIsDefault"
                class="ml-1 rounded-full bg-warn-soft px-2 py-0.5 text-[10px] font-semibold text-warn"
                title="Nobody has entered this person's hours; this is the default"
                >Default</span
              >
            </td>
            <td class="px-3 py-2">{{ MODE[e.workMode] ?? e.workMode }}</td>
            <td class="px-3 py-2">
              {{ e.skills.map((s) => `${s.queue} L${s.level}`).join(', ') || '—' }}
            </td>
            <td class="px-3 py-2">{{ e.manager ?? '—' }}</td>
            <td class="px-3 py-2">{{ e.agentLogins.join(', ') || '—' }}</td>
            <td class="px-4 py-2 text-right">
              <button
                v-if="canChange"
                type="button"
                class="text-sm font-medium text-brand-ink underline"
                :aria-label="`Change ${e.name}`"
                @click="editing = e"
              >
                Change
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
