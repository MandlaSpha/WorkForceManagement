<script setup lang="ts">
import { useRouter } from 'vue-router'

import { homePathFor, useSessionStore } from '@/entities/session'
import { ChangePasswordForm } from '@/features/account/change-password'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

const router = useRouter()
const session = useSessionStore()
const forced = session.user?.mustChangePassword === true

function changed(): void {
  void router.push(session.user ? homePathFor(session.user.role) : '/')
}
</script>

<template>
  <main class="mx-auto max-w-lg space-y-4 p-6">
    <h1 class="text-xl font-semibold text-ink">Change your password</h1>
    <NoticeBox v-if="forced" data-testid="forced-notice">
      An admin gave your account a temporary password. Choose your own before you carry on.
    </NoticeBox>
    <ChangePasswordForm @changed="changed" />
  </main>
</template>
