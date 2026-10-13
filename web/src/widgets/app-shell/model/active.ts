/**
 * Is this sidebar entry the screen the user is on? "/" is a prefix of every address, so the
 * dashboard link must match the dashboard alone; every other entry matches its own path and
 * anything below it ("/leave" and "/leave/42", but not "/leaves").
 */
export function isActivePath(itemPath: string, currentPath: string): boolean {
  const trimmed = currentPath.replace(/\/+$/, '')
  const here = trimmed === '' ? '/' : trimmed
  if (itemPath === '/') return here === '/'
  return here === itemPath || here.startsWith(`${itemPath}/`)
}
