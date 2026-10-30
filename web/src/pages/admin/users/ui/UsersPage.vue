<script setup lang="ts">
import { computed, ref } from 'vue'

import { useEmployees } from '@/entities/scheduling'
import { ROLE_LABELS, ROLES, useSessionStore } from '@/entities/session'
import { useUsers } from '@/entities/user-admin'
import { CreateUserForm, UserRow } from '@/features/people/users'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'
import StatTile from '@/shared/ui/StatTile.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'users')
const session = useSessionStore()
const users = useUsers()
const employees = useEmployees(null)

// "Linked" is read from the employee side: the user list carries the number, the employee list
// carries the name, and one login belongs to one employee.
const byNumber = computed(() => new Map((employees.data.value ?? []).map((e) => [e.empNo, e])))
// ---- find someone: by name, username or employee number, then by role or state ----
const search = ref('')
const role = ref<string | null>(null)
const state = ref<'active' | 'inactive' | 'locked' | null>(null)
const everyone = computed(() => users.data.value ?? [])
const count = (test: (u: (typeof everyone.value)[number]) => boolean): number =>
  everyone.value.filter(test).length
const shown = computed(() => {
  const needle = search.value.trim().toLowerCase()
  return everyone.value.filter(
    (u) =>
      (role.value === null || u.role === role.value) &&
      (state.value === null ||
        (state.value === 'active' && u.active) ||
        (state.value === 'inactive' && !u.active) ||
        (state.value === 'locked' && u.locked)) &&
      (needle === '' ||
        u.name.toLowerCase().includes(needle) ||
        u.username.toLowerCase().includes(needle) ||
        (u.employee ?? '').toLowerCase().includes(needle)),
  )
})
const STATES = [
  { key: 'active', label: 'Active' },
  { key: 'inactive', label: 'Switched off' },
  { key: 'locked', label: 'Locked' },
] as const
const free = computed(() => (employees.data.value ?? []).filter((e) => !e.hasLogin))
</script>

<template>
  <PageHeader eyebrow="Admin" :title="screen?.label ?? 'Users'" :subtitle="screen?.subtitle" />

  <div class="space-y-6" aria-live="polite">
    <section class="space-y-2" aria-labelledby="list-title">
      <h2 id="list-title" class="text-base font-semibold text-ink">Everyone who can sign in</h2>
      <p v-if="users.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="users.isError.value" tone="danger">
        Could not load the users. {{ problemMessage(users.error.value) }}
      </NoticeBox>
      <template v-else>
        <ul class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Accounts">
          <StatTile label="Accounts" :value="everyone.length" tint="brand" />
          <StatTile label="Active" :value="count((u) => u.active)" tint="ok" />
          <StatTile label="Locked" :value="count((u) => u.locked)" tint="danger" />
          <StatTile
            label="Must change password"
            :value="count((u) => u.mustChangePassword)"
            tint="warn"
          />
        </ul>

        <div
          class="flex flex-wrap items-center gap-x-2 gap-y-2"
          role="group"
          aria-label="Find a user"
        >
          <label class="block w-full sm:w-72">
            <span class="sr-only">Search by name, username or employee number</span>
            <input
              v-model="search"
              type="search"
              placeholder="Search by name, username or number"
              class="min-h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm text-ink"
              data-testid="user-search"
            />
          </label>
          <button
            type="button"
            class="press rounded-full px-3 py-1.5 text-sm"
            :class="
              role === null && state === null
                ? 'bg-brand text-brand-contrast'
                : 'bg-surface text-ink'
            "
            :aria-pressed="role === null && state === null"
            @click="((role = null), (state = null))"
          >
            All <span class="opacity-70">{{ everyone.length }}</span>
          </button>
          <button
            v-for="r in ROLES.filter((x) => count((u) => u.role === x) > 0)"
            :key="r"
            type="button"
            class="press rounded-full px-3 py-1.5 text-sm"
            :class="role === r ? 'bg-brand text-brand-contrast' : 'bg-surface text-ink'"
            :aria-pressed="role === r"
            @click="role = role === r ? null : r"
          >
            {{ ROLE_LABELS[r] }} <span class="opacity-70">{{ count((u) => u.role === r) }}</span>
          </button>
          <span class="mx-1 hidden h-6 w-px bg-line sm:block" aria-hidden="true"></span>
          <button
            v-for="st in STATES"
            :key="st.key"
            type="button"
            class="press rounded-full px-3 py-1.5 text-sm"
            :class="state === st.key ? 'bg-ink text-canvas' : 'bg-surface text-ink'"
            :aria-pressed="state === st.key"
            @click="state = state === st.key ? null : st.key"
          >
            {{ st.label }}
          </button>
        </div>

        <NoticeBox v-if="shown.length === 0" data-testid="no-match">Nobody matches that.</NoticeBox>
        <div v-else class="overflow-x-auto rounded-xl border border-line bg-surface">
          <table class="w-full min-w-[48rem] text-left text-sm" data-testid="users-table">
            <caption class="sr-only">
              Users
            </caption>
            <thead class="border-b border-line bg-surface-muted text-xs text-ink-muted">
              <tr>
                <th scope="col" class="px-4 py-2 font-medium">Person</th>
                <th scope="col" class="px-3 py-2 font-medium">Role</th>
                <th scope="col" class="px-3 py-2 font-medium">Status</th>
                <th scope="col" class="px-3 py-2 font-medium">Employee</th>
                <th scope="col" class="px-3 py-2 text-right font-medium">
                  <span class="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              <UserRow
                v-for="u in shown"
                :key="u.id"
                :user="u"
                :own="u.username === session.user?.username"
                :free="free"
                :linked="u.employee ? (byNumber.get(u.employee) ?? null) : null"
              />
            </tbody>
          </table>
        </div>
      </template>
    </section>

    <details class="rounded-2xl border border-line bg-surface p-4" data-testid="add-user">
      <summary class="cursor-pointer text-base font-semibold text-ink">Add a user</summary>
      <div class="mt-3"><CreateUserForm /></div>
    </details>
  </div>
</template>
