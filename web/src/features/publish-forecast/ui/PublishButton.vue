<script setup lang="ts">
import type { ForecastVersion } from '@/entities/forecast'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'

import { usePublishForecast } from '../model/usePublishForecast'

const props = defineProps<{ version: ForecastVersion }>()
const publish = usePublishForecast()
</script>

<template>
  <div class="inline-flex flex-col items-end gap-1">
    <AppButton
      variant="secondary"
      :loading="publish.isPending.value"
      :aria-label="`Publish ${props.version.label || 'forecast'} for ${props.version.queue}`"
      @click="publish.mutate(props.version.id)"
    >
      Publish
    </AppButton>
    <p v-if="publish.isError.value" class="max-w-56 text-right text-xs text-danger" role="alert">
      {{ problemMessage(publish.error.value) }}
    </p>
  </div>
</template>
