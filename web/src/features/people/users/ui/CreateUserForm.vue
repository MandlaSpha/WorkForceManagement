<script setup lang="ts">
import { ref } from 'vue'

import { ROLE_LABELS, ROLES } from '@/entities/session'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import SelectField from '@/shared/ui/SelectField.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useUserActions } from '../model/useUserActions'

const { create } = useUserActions()
const username = ref('')
const firstName = ref('')
const lastName = ref('')
const role = ref('agent')
const password = ref('')
const ROLE_OPTIONS = ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] }))

function submit(): void {
  create.mutate(
    {
      username: username.value.trim(),
      firstName: firstName.value.trim(),
      lastName: lastName.value.trim(),
      role: role.value,
      password: password.value,
    },
    {
      onSuccess: () => {
        username.value = ''
        firstName.value = ''
        lastName.value = ''
        password.value = ''
      },
    },
  )
}
</script>

<template>
  <form class="space-y-3" aria-label="Add a user" @submit.prevent="submit">
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <TextField v-model="username" label="Username" autocomplete="off" />
      <TextField v-model="firstName" label="First name" autocomplete="off" />
      <TextField v-model="lastName" label="Last name" autocomplete="off" />
      <SelectField v-model="role" label="Role" :options="ROLE_OPTIONS" />
      <TextField
        v-model="password"
        type="password"
        label="Temporary password"
        autocomplete="new-password"
      />
    </div>
    <p class="text-xs text-ink-muted">
      They must choose their own password the first time they sign in. At least 12 characters.
      People who sign in through your identity provider need no account here.
    </p>
    <AppButton
      type="submit"
      :loading="create.isPending.value"
      :disabled="username.trim() === '' || password === ''"
    >
      Add user
    </AppButton>
    <NoticeBox v-if="create.isError.value" tone="danger" data-testid="create-error">
      <p class="font-medium">The user was not added.</p>
      <p>{{ problemMessage(create.error.value) }}</p>
    </NoticeBox>
    <NoticeBox v-else-if="create.data.value" data-testid="create-result">
      Added {{ create.data.value.username }}. Give them the temporary password in person; they will
      be asked to change it.
    </NoticeBox>
  </form>
</template>
