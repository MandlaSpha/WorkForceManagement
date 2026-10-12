/** Accept a post-login redirect only if it is a same-site path, so a crafted link cannot send a
 * freshly signed-in user to another origin (open redirect). */
export function safeRedirect(target: unknown, fallback = '/'): string {
  if (typeof target !== 'string') return fallback
  if (!target.startsWith('/') || target.startsWith('//') || target.includes('\\')) return fallback
  if (target.startsWith('/login')) return fallback
  return target
}
