<script setup lang="ts">
import { computed } from 'vue'

import { useEmployees } from '@/entities/scheduling'
import { useSessionStore } from '@/entities/session'
import { useUsers } from '@/entities/user-admin'
import { CreateUserForm, UserRow } from '@/features/people/users'
import { problemMessage } from '@/shared/api'
import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'users')
const session = useSessionStore()
const users = useUsers()
const employees = useEmployees(null)

// "Linked" is read from the employee side: the user list carries the number, the employee list
// carries the name, and one login belongs to one employee.
const byNumber = computed(() => new Map((employees.data.value ?? []).map((e) => [e.empNo, e])))
const free = computed(() => (employees.data.value ?? []).filter((e) => !e.hasLogin))
</script>

<template>
  <PageHeader eyebrow="Admin" :title="screen?.label ?? 'Users'" :subtitle="screen?.subtitle" />

  <div class="space-y-6" aria-live="polite">
    <section class="space-y-2" aria-labelledby="add-title">
      <h2 id="add-title" class="text-base font-semibold text-ink">Add a user</h2>
      <CreateUserForm />
    </section>

    <section class="space-y-2" aria-labelledby="list-title">
      <h2 id="list-title" class="text-base font-semibold text-ink">Everyone who can sign in</h2>
      <p v-if="users.isPending.value" class="text-sm text-ink-muted">Loading…</p>
      <NoticeBox v-else-if="users.isError.value" tone="danger">
        Could not load the users. {{ problemMessage(users.error.value) }}
      </NoticeBox>
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
              v-for="u in users.data.value"
              :key="u.id"
              :user="u"
              :own="u.username === session.user?.username"
              :free="free"
              :linked="u.employee ? (byNumber.get(u.employee) ?? null) : null"
            />
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
