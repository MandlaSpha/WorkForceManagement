<script setup lang="ts">
import { toRef } from 'vue'

import { useCountUp } from './useCountUp'

const props = withDefaults(defineProps<{ value: number; format?: (n: number) => string }>(), {
  format: (n: number) => Math.round(n).toLocaleString('en-ZA'),
})
const { text, shown, animating } = useCountUp(toRef(props, 'value'), (n) => props.format(n))
</script>

<template>
  <template v-if="animating">
    <span aria-hidden="true">{{ shown }}</span>
    <span class="sr-only">{{ text }}</span>
  </template>
  <template v-else>{{ text }}</template>
</template>
