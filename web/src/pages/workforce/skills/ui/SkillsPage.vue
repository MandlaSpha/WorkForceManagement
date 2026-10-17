<script setup lang="ts">
import { computed, ref } from 'vue'

import { useEmployees } from '@/entities/scheduling'
import { useSessionStore } from '@/entities/session'
import {
  CREDENTIAL_KINDS,
  KIND_LABEL,
  useCredentials,
  useGaps,
  useRequirements,
} from '@/entities/workforce/skills'
import { useContextStore } from '@/features/context-filters'
import { CredentialEditor } from '@/features/skills/edit-credentials'
import { RequirementEditor } from '@/features/skills/edit-requirements'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const GAP_DAYS = 7
const context = useContextStore()
const session = useSessionStore()
const screen = NAV_ITEMS.find((item) => item.key === 'skills')
// Cosmetic: the API refuses everyone but a planner or admin.
const canEdit = computed(() => ['planner', 'admin'].includes(session.user?.role ?? ''))

// One person's credentials.
const people = useEmployees()
const employeeId = ref<number | null>(null)
const credentials = useCredentials(employeeId)
const chosen = computed(() => people.data.value?.find((p) => p.id === employeeId.value))
const shown = computed(() =>
  (credentials.data.value ?? []).filter((c) => c.employeeId === employeeId.value),
)

// Who holds a credential (the same filter the roster can use).
const findKind = ref<string>('language')
const findName = ref('')
const wanted = computed(() =>
  findName.value.trim() ? `${findKind.value}:${findName.value.trim()}` : null,
)
const holders = useEmployees(
  null,
  computed(() => wanted.value !== null),
  wanted,
)

// What the chosen queue requires, and where the roster falls short.
const queueId = computed(() => context.queueNumber)
const requirements = useRequirements(queueId)
const gaps = useGaps(
  computed(() => context.weekStart),
  GAP_DAYS,
  canEdit,
)
const queueName = computed(() => context.queueNumber)
const queueGaps = computed(() =>
  (gaps.data.value ?? []).filter((g) => queueName.value === null || g.queueId === queueName.value),
)
</script>

<template>
  <PageHeader eyebrow="People" :title="screen?.label ?? 'Skills'" :subtitle="screen?.subtitle" />

  <div class="space-y-6">
    <section
      class="space-y-3 rounded-xl border border-line bg-surface p-4"
      aria-labelledby="cred-title"
    >
      <h2 id="cred-title" class="text-sm font-semibold text-ink">
        Certifications, languages and clearances
      </h2>
      <p v-if="people.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="people.isError.value" tone="danger">
        Could not load the employees. {{ problemMessage(people.error.value) }}
      </NoticeBox>
      <template v-else>
        <label class="block text-sm font-medium text-ink">
          Employee
          <select
            v-model="employeeId"
            class="mt-1 block w-full max-w-sm rounded-lg border border-line bg-surface px-2 py-1.5 text-sm"
          >
            <option :value="null">Choose an employee</option>
            <option v-for="p in people.data.value" :key="p.id" :value="p.id">
              {{ p.name }} ({{ p.empNo }})
            </option>
          </select>
        </label>

        <template v-if="chosen">
          <p v-if="credentials.isPending.value" class="text-sm text-ink-muted">Loading…</p>
          <NoticeBox v-else-if="credentials.isError.value" tone="danger">
            Could not load the credentials. {{ problemMessage(credentials.error.value) }}
          </NoticeBox>
          <template v-else>
            <p v-if="shown.length === 0" class="text-sm text-ink-muted" data-testid="none-held">
              Nothing recorded for {{ chosen.name }}.
            </p>
            <ul
              v-else
              class="flex flex-wrap gap-2"
              aria-label="Credentials held"
              data-testid="held"
            >
              <li
                v-for="c in shown"
                :key="`${c.kind}:${c.name}`"
                class="rounded-full border border-line px-3 py-1 text-xs text-ink"
              >
                {{ KIND_LABEL[c.kind] ?? c.kind }}: {{ c.name }}
                <span
                  v-if="c.expiresOn"
                  :class="c.expired ? 'font-semibold text-danger' : 'text-ink-muted'"
                >
                  ({{ c.expired ? 'expired' : 'to' }} {{ c.expiresOn }})
                </span>
              </li>
            </ul>
            <CredentialEditor
              v-if="canEdit"
              :employee-id="chosen.id"
              :credentials="shown"
              data-testid="credential-editor"
            />
          </template>
        </template>
      </template>
    </section>

    <section
      class="space-y-3 rounded-xl border border-line bg-surface p-4"
      aria-labelledby="find-title"
    >
      <h2 id="find-title" class="text-sm font-semibold text-ink">Who holds a credential</h2>
      <div class="flex flex-wrap items-end gap-2">
        <label class="text-xs text-ink-muted">
          Kind
          <select
            v-model="findKind"
            class="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option v-for="k in CREDENTIAL_KINDS" :key="k" :value="k">{{ KIND_LABEL[k] }}</option>
          </select>
        </label>
        <label class="text-xs text-ink-muted">
          Credential name
          <input
            v-model="findName"
            class="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </label>
      </div>
      <div aria-live="polite">
        <p v-if="wanted === null" class="text-sm text-ink-muted">
          Type a name to see who holds it today.
        </p>
        <p v-else-if="holders.isPending.value" class="text-sm text-ink-muted">Loading…</p>
        <p
          v-else-if="(holders.data.value ?? []).length === 0"
          class="text-sm text-ink-muted"
          data-testid="no-holders"
        >
          Nobody holds it today.
        </p>
        <ul v-else class="list-disc pl-5 text-sm text-ink" data-testid="holders">
          <li v-for="p in holders.data.value" :key="p.id">{{ p.name }} ({{ p.empNo }})</li>
        </ul>
      </div>
    </section>

    <section
      class="space-y-3 rounded-xl border border-line bg-surface p-4"
      aria-labelledby="req-title"
    >
      <h2 id="req-title" class="text-sm font-semibold text-ink">
        What the queue requires, and where it is short
      </h2>
      <NoticeBox v-if="queueId === null">Choose a queue at the top of the page.</NoticeBox>
      <template v-else>
        <p v-if="requirements.isPending.value" class="text-sm text-ink-muted">Loading…</p>
        <NoticeBox v-else-if="requirements.isError.value" tone="danger">
          Could not load the requirements. {{ problemMessage(requirements.error.value) }}
        </NoticeBox>
        <template v-else>
          <p
            v-if="(requirements.data.value ?? []).length === 0"
            class="text-sm text-ink-muted"
            data-testid="no-requirements"
          >
            This queue has no required skills, so no gaps can be found.
          </p>
          <ul v-else class="list-disc pl-5 text-sm text-ink" data-testid="requirements">
            <li v-for="r in requirements.data.value" :key="`${r.kind}:${r.name}`">
              {{ KIND_LABEL[r.kind] ?? r.kind }}: {{ r.name }}, at least {{ r.minPeople }} on every
              shift
            </li>
          </ul>
          <RequirementEditor
            v-if="canEdit"
            :queue-id="queueId"
            :requirements="requirements.data.value ?? []"
            data-testid="requirement-editor"
          />
        </template>

        <div v-if="canEdit" aria-live="polite" class="space-y-2">
          <h3 class="text-sm font-semibold text-ink">Skill gaps this week</h3>
          <p v-if="gaps.isPending.value" class="text-sm text-ink-muted">Loading…</p>
          <NoticeBox v-else-if="gaps.isError.value" tone="danger">
            Could not load the gaps. {{ problemMessage(gaps.error.value) }}
          </NoticeBox>
          <p
            v-else-if="queueGaps.length === 0"
            class="text-sm text-ink-muted"
            data-testid="no-gaps"
          >
            No shift this week is short of a required skill.
          </p>
          <div v-else class="overflow-x-auto">
            <table class="w-full text-left text-sm" data-testid="gaps">
              <caption class="sr-only">
                Shifts short of a required skill
              </caption>
              <thead class="text-xs text-ink-muted">
                <tr>
                  <th scope="col" class="px-3 py-2">Day</th>
                  <th scope="col" class="px-3 py-2">Shift</th>
                  <th scope="col" class="px-3 py-2">Skill</th>
                  <th scope="col" class="px-3 py-2">Have / need</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="g in queueGaps"
                  :key="`${g.queueId}${g.day}${g.shiftCode}${g.kind}${g.name}`"
                  class="border-t border-line"
                >
                  <td class="px-3 py-2">{{ g.day }}</td>
                  <td class="px-3 py-2">{{ g.shiftCode }}</td>
                  <td class="px-3 py-2">{{ KIND_LABEL[g.kind] ?? g.kind }}: {{ g.name }}</td>
                  <td class="px-3 py-2 font-semibold text-warn">
                    {{ g.present }} of {{ g.required }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>
