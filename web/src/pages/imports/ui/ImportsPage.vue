<script setup lang="ts">
import { ImportHistory, ImportPanel } from '@/features/import-call-data'
import { NAV_ITEMS } from '@/shared/config'
import PageHeader from '@/shared/ui/PageHeader.vue'

const screen = NAV_ITEMS.find((item) => item.key === 'imports')
</script>

<template>
  <PageHeader
    eyebrow="Operate"
    :title="screen?.label ?? 'Data import'"
    :subtitle="screen?.subtitle"
  />
  <div class="space-y-10">
    <ImportPanel />
    <ImportHistory />
  </div>
</template>
