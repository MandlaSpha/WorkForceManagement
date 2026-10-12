<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { NAV_ITEMS } from '@/shared/config'
import NoticeBox from '@/shared/ui/NoticeBox.vue'
import PageHeader from '@/shared/ui/PageHeader.vue'

const route = useRoute()
const item = computed(() => NAV_ITEMS.find((i) => i.key === route.meta.navKey))
</script>

<template>
  <template v-if="item">
    <PageHeader :title="item.label" :subtitle="item.subtitle" />
    <NoticeBox>
      This screen is built in Phase {{ item.phase }}. It shows nothing yet rather than sample
      figures.
    </NoticeBox>
  </template>
</template>
