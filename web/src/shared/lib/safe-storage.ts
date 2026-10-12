/** localStorage can throw (private windows, blocked site data), so every access is guarded and
 * the app must render correctly without it. Use only for per-viewer conveniences. */
export const safeStorage = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key)
    } catch {
      return null
    }
  },
  set(key: string, value: string): void {
    try {
      localStorage.setItem(key, value)
    } catch {
      // storage unavailable: the preference simply is not remembered
    }
  },
}
