<script setup lang="ts">
import { ref, useId, watch } from 'vue'

import { CREDENTIAL_KINDS, KIND_LABEL, type Credential } from '@/entities/workforce/skills'
import { problemMessage } from '@/shared/api'
import AppButton from '@/shared/ui/AppButton.vue'
import NoticeBox from '@/shared/ui/NoticeBox.vue'

import { useSaveCredentials } from '../model/useSaveCredentials'

const props = defineProps<{ employeeId: number; credentials: Credential[] }>()

interface Row {
  key: number
  kind: string
  name: string
  expiresOn: string
}
let next = 0
const rows = ref<Row[]>([])
const save = useSaveCredentials()
const formId = useId()

function reset(): void {
  rows.value = props.credentials.map((c) => ({
    key: next++,
    kind: c.kind,
    name: c.name,
    expiresOn: c.expiresOn ?? '',
  }))
}
watch(() => [props.employeeId, props.credentials], reset, { immediate: true })

function add(): void {
  rows.value.push({ key: next++, kind: 'certification', name: '', expiresOn: '' })
}

function submit(): void {
  save.mutate({
    employeeId: props.employeeId,
    credentials: rows.value
      .filter((r) => r.name.trim() !== '')
      .map((r) => ({ kind: r.kind, name: r.name, expiresOn: r.expiresOn || null })),
  })
}
</script>

<template>
  <form class="space-y-3" :aria-labelledby="formId" @submit.prevent="submit">
    <h3 :id="formId" class="text-sm font-semibold text-ink">Edit credentials</h3>
    <p v-if="rows.length === 0" class="text-sm text-ink-muted" data-testid="no-credentials">
      No credentials recorded.
    </p>
    <ul class="space-y-2">
      <li v-for="(row, i) in rows" :key="row.key" class="flex flex-wrap items-end gap-2">
        <label class="text-xs text-ink-muted">
          Kind
          <select
            v-model="row.kind"
            class="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            :aria-label="`Kind of credential ${i + 1}`"
          >
            <option v-for="k in CREDENTIAL_KINDS" :key="k" :value="k">{{ KIND_LABEL[k] }}</option>
          </select>
        </label>
        <label class="text-xs text-ink-muted">
          Name
          <input
            v-model="row.name"
            maxlength="80"
            class="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            :aria-label="`Name of credential ${i + 1}`"
          />
        </label>
        <label class="text-xs text-ink-muted">
          Expires (optional)
          <input
            v-model="row.expiresOn"
            type="date"
            class="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            :aria-label="`Expiry of credential ${i + 1}`"
          />
        </label>
        <AppButton
          variant="ghost"
          :aria-label="`Remove credential ${i + 1}`"
          @click="rows.splice(i, 1)"
        >
          Remove
        </AppButton>
      </li>
    </ul>
    <div class="flex gap-2">
      <AppButton variant="secondary" @click="add">Add credential</AppButton>
      <AppButton type="submit" :loading="save.isPending.value">Save credentials</AppButton>
    </div>
    <div aria-live="polite">
      <NoticeBox v-if="save.isError.value" tone="danger" data-testid="credentials-error">
        {{ problemMessage(save.error.value) }}
      </NoticeBox>
      <p
        v-else-if="save.isSuccess.value"
        class="text-sm text-ink-muted"
        data-testid="credentials-saved"
      >
        Saved.
      </p>
    </div>
  </form>
</template>
