<script setup lang="ts">
import { computed, ref } from 'vue'

import type { Employee } from '@/entities/scheduling'
import { ROLE_LABELS, ROLES } from '@/entities/session'
import type { AdminUser } from '@/entities/user-admin'
import { problemMessage } from '@/shared/api'

import { useUserActions } from '../model/useUserActions'

const props = defineProps<{
  user: AdminUser
  own: boolean
  /** Employees with no login yet: who this account could be. */
  free: ReadonlyArray<Employee>
  /** The employee this account is linked to, if any. */
  linked: Employee | null
}>()

const actions = useUserActions()
const resetting = ref(false)
const password = ref('')
const pick = ref('')

const roleOptions = ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] }))
const roleLabel = computed(
  () => ROLE_LABELS[props.user.role as keyof typeof ROLE_LABELS] ?? props.user.role,
)
const failure = computed(() => {
  for (const m of [actions.role, actions.active, actions.unlock, actions.reset, actions.link]) {
    if (m.isError.value) return problemMessage(m.error.value)
  }
  return ''
})

function changeRole(event: Event): void {
  actions.role.mutate({ id: props.user.id, role: (event.target as HTMLSelectElement).value })
}
function reset(): void {
  actions.reset.mutate(
    { id: props.user.id, password: password.value },
    {
      onSuccess: () => {
        resetting.value = false
        password.value = ''
      },
    },
  )
}
function link(): void {
  if (pick.value === '') return
  actions.link.mutate({ employeeId: Number(pick.value), userId: props.user.id })
}
</script>

<template>
  <tr class="border-b border-line align-top" :data-testid="`user-${user.username}`">
    <th scope="row" class="px-4 py-2 text-left font-medium text-ink">
      {{ user.name }}
      <span class="block text-xs font-normal text-ink-muted">{{ user.username }}</span>
    </th>
    <td class="px-3 py-2">
      <span v-if="own || user.roleFromDirectory" :data-testid="`role-fixed-${user.username}`">
        {{ roleLabel }}
        <span v-if="user.roleFromDirectory" class="block text-xs text-ink-muted">
          set by the identity provider's groups
        </span>
        <span v-else class="block text-xs text-ink-muted">your own role</span>
      </span>
      <select
        v-else
        :value="user.role"
        class="rounded-md border border-line bg-surface px-1 py-1 text-sm text-ink"
        :aria-label="`Role of ${user.username}`"
        @change="changeRole"
      >
        <option v-for="r in roleOptions" :key="r.value" :value="r.value">{{ r.label }}</option>
      </select>
    </td>
    <td class="px-3 py-2 text-sm">
      <span v-if="!user.active" class="font-medium text-danger">Switched off</span>
      <span v-else-if="user.locked" class="font-medium text-warn">Locked</span>
      <span v-else>Active</span>
      <span v-if="user.mustChangePassword" class="block text-xs text-ink-muted">
        must choose a password
      </span>
      <span v-if="!user.hasPassword" class="block text-xs text-ink-muted">
        signs in through the provider
      </span>
    </td>
    <td class="px-3 py-2 text-sm">
      <template v-if="linked">
        {{ linked.name }} <span class="text-ink-muted">({{ linked.empNo }})</span>
        <button
          type="button"
          class="ml-2 text-xs font-medium text-danger underline"
          :aria-label="`Unlink ${user.username} from ${linked.name}`"
          @click="actions.link.mutate({ employeeId: linked.id, userId: null })"
        >
          Unlink
        </button>
      </template>
      <div v-else-if="free.length > 0" class="flex items-center gap-1">
        <select
          v-model="pick"
          class="max-w-40 rounded-md border border-line bg-surface px-1 py-1 text-xs text-ink"
          :aria-label="`Employee for ${user.username}`"
        >
          <option value="">Not an employee</option>
          <option v-for="e in free" :key="e.id" :value="String(e.id)">
            {{ e.name }} ({{ e.empNo }})
          </option>
        </select>
        <button
          type="button"
          class="text-xs font-medium text-brand-ink underline disabled:opacity-60"
          :disabled="pick === ''"
          :aria-label="`Link ${user.username} to the chosen employee`"
          @click="link"
        >
          Link
        </button>
      </div>
      <span v-else class="text-ink-muted">Not an employee</span>
    </td>
    <td class="px-3 py-2 text-right text-xs">
      <div class="flex flex-col items-end gap-1">
        <button
          v-if="user.locked"
          type="button"
          class="font-medium text-brand-ink underline"
          :aria-label="`Unlock ${user.username}`"
          @click="actions.unlock.mutate(user.id)"
        >
          Unlock
        </button>
        <button
          v-if="user.hasPassword && !resetting"
          type="button"
          class="font-medium text-brand-ink underline"
          :aria-label="`Set a new temporary password for ${user.username}`"
          @click="resetting = true"
        >
          New password
        </button>
        <form v-if="resetting" class="flex items-center gap-1" @submit.prevent="reset">
          <input
            v-model="password"
            type="password"
            autocomplete="new-password"
            class="w-32 rounded-md border border-line bg-surface px-1 py-1 text-xs text-ink"
            :aria-label="`Temporary password for ${user.username}`"
          />
          <button
            type="submit"
            class="font-medium text-brand-ink underline"
            :disabled="password === ''"
          >
            Set
          </button>
          <button type="button" class="text-ink-muted underline" @click="resetting = false">
            Cancel
          </button>
        </form>
        <button
          v-if="!own"
          type="button"
          class="font-medium underline"
          :class="user.active ? 'text-danger' : 'text-brand-ink'"
          :aria-label="`${user.active ? 'Switch off' : 'Switch on'} ${user.username}`"
          @click="actions.active.mutate({ id: user.id, active: !user.active })"
        >
          {{ user.active ? 'Switch off' : 'Switch on' }}
        </button>
        <span v-if="failure" class="text-danger" role="alert">{{ failure }}</span>
      </div>
    </td>
  </tr>
</template>
