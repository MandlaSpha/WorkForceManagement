<script setup lang="ts">
import { ref, watch } from 'vue'

import AppButton from './AppButton.vue'
import Dialog from './Dialog.vue'
import TextField from './TextField.vue'

/** Asks for a reason before something is turned down. The reason is required: an empty one is
 * refused here, with a message, and nothing is confirmed. */
const props = defineProps<{ title: string; subtitle?: string; confirmLabel: string }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ confirm: [reason: string] }>()

const reason = ref('')
const error = ref('')
watch(
  () => open.value,
  (isOpen) => {
    if (isOpen) {
      reason.value = ''
      error.value = ''
    }
  },
)

function submit(): void {
  const text = reason.value.trim()
  if (text === '') {
    error.value = 'Give a reason.'
    return
  }
  emit('confirm', text)
  open.value = false
}
</script>

<template>
  <Dialog v-model:open="open" :title="props.title" :subtitle="props.subtitle" size="sm">
    <form id="reason-form" @submit.prevent="submit">
      <TextField v-model="reason" label="Reason" :error="error" />
    </form>
    <template #footer>
      <AppButton variant="secondary" @click="open = false">Keep it as it is</AppButton>
      <AppButton type="submit" form="reason-form">{{ props.confirmLabel }}</AppButton>
    </template>
  </Dialog>
</template>
