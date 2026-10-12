<script setup lang="ts">
import { LogOut } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useSessionStore } from '@/entities/session'
import AppButton from '@/shared/ui/AppButton.vue'

const session = useSessionStore()
const router = useRouter()
const busy = ref(false)

async function signOut(): Promise<void> {
  busy.value = true
  try {
    await session.signOut()
    await router.push('/login')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <AppButton variant="ghost" :loading="busy" @click="signOut">
    <LogOut :size="16" aria-hidden="true" />
    Sign out
  </AppButton>
</template>
