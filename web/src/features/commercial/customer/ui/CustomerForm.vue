<script setup lang="ts">
import { ref } from 'vue'

import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import TextField from '@/shared/ui/TextField.vue'

import { useAddCustomer } from '../model/useAddCustomer'

const name = ref('')
const add = useAddCustomer()

function submit(): void {
  add.mutate(name.value.trim(), { onSuccess: () => (name.value = '') })
}
</script>

<template>
  <form class="flex flex-wrap items-end gap-3" aria-label="Add a customer" @submit.prevent="submit">
    <div class="w-64"><TextField v-model="name" label="Customer name" /></div>
    <AppButton type="submit" :loading="add.isPending.value" :disabled="name.trim() === ''">
      Add customer
    </AppButton>
    <NoticeBox v-if="add.isError.value" tone="danger" data-testid="customer-error">
      {{ problemMessage(add.error.value) }}
    </NoticeBox>
  </form>
</template>
