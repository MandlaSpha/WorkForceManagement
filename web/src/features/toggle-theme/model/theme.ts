import { defineStore } from 'pinia'
import { ref } from 'vue'

import { safeStorage } from '@/shared/lib/safe-storage'

const KEY = 'wfm.theme'

function systemPrefersDark(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches
}

export const useThemeStore = defineStore('theme', () => {
  const stored = safeStorage.get(KEY)
  const dark = ref(stored ? stored === 'dark' : systemPrefersDark())

  function apply(): void {
    document.documentElement.classList.toggle('dark', dark.value)
  }

  function toggle(): void {
    dark.value = !dark.value
    safeStorage.set(KEY, dark.value ? 'dark' : 'light')
    apply()
  }

  apply()
  return { dark, toggle }
})
