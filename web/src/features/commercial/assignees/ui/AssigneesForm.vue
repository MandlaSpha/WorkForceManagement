<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'

import { useAssignees } from '@/entities/contract'
import type { Customer } from '@/entities/contract'
import { useUsers } from '@/entities/user-admin'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useSetAssignees } from '../model/useSetAssignees'

const props = defineProps<{ customer: Customer }>()

const assignees = useAssignees(toRef(() => props.customer.id))
const users = useUsers()
const save = useSetAssignees()

// Only active customer operations managers can be given a customer.
const managers = computed(() =>
  (users.data.value ?? []).filter((u) => u.role === 'customer_ops' && u.active),
)
const chosen = ref<number[]>([])
watch(
  () => assignees.data.value,
  (found) => (chosen.value = (found ?? []).map((a) => a.id)),
  { immediate: true },
)

function toggle(id: number, on: boolean): void {
  chosen.value = on ? [...chosen.value, id] : chosen.value.filter((x) => x !== id)
}

function submit(): void {
  save.mutate({ customerId: props.customer.id, userIds: chosen.value })
}
</script>

<template>
  <form
    class="space-y-2 rounded-xl border border-line bg-surface p-4"
    :aria-label="`Who looks after ${customer.name}`"
    @submit.prevent="submit"
  >
    <fieldset class="space-y-1">
      <legend class="text-sm font-medium text-ink">
        {{ customer.name }}: customer operations managers
      </legend>
      <p v-if="managers.length === 0" class="text-sm text-ink-muted">
        There is no active customer operations manager. Add one under Users.
      </p>
      <label v-for="m in managers" :key="m.id" class="flex items-center gap-2 text-sm text-ink">
        <input
          type="checkbox"
          :checked="chosen.includes(m.id)"
          @change="toggle(m.id, ($event.target as HTMLInputElement).checked)"
        />
        {{ m.name }}
      </label>
    </fieldset>
    <p class="text-xs text-ink-muted">
      A manager sees only the customers chosen here, with their contracts and queues. With none
      chosen they see nothing.
    </p>
    <AppButton type="submit" :loading="save.isPending.value">Save who looks after it</AppButton>
    <NoticeBox v-if="save.isError.value" tone="danger" data-testid="assignees-error">
      {{ problemMessage(save.error.value) }}
    </NoticeBox>
  </form>
</template>
