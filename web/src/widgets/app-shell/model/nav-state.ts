import type { NavGroup } from '@/shared/config'

import { isActivePath } from './active'
import type { VisibleGroup } from './visible-nav'

/** Where the sidebar remembers which groups a person left open. Not personal data: group names. */
export const NAV_OPEN_KEY = 'wfm.nav.open'

/** The group holding the screen being looked at, so the sidebar never hides where you are. */
export function activeGroup(groups: readonly VisibleGroup[], path: string): NavGroup | null {
  return groups.find((g) => g.items.some((i) => isActivePath(i.path, path)))?.group ?? null
}

/** Groups to show open: the ones the person chose (an accordion keeps it to one), or, when they
 * have chosen none, the one they are in. Unknown names in what was remembered (a group renamed or
 * removed since) are ignored. */
export function openGroups(
  groups: readonly VisibleGroup[],
  path: string,
  remembered: readonly string[],
): Set<NavGroup> {
  const open = new Set<NavGroup>()
  for (const g of groups) if (remembered.includes(g.group)) open.add(g.group)
  const here = activeGroup(groups, path)
  if (open.size === 0 && here) open.add(here)
  return open
}

/** What to remember after a click on a group. Opening one closes the rest, so the menu never
 * grows into a long list; clicking the one that is open closes it. */
export function afterClick(open: ReadonlySet<NavGroup>, group: NavGroup): NavGroup[] {
  return open.has(group) ? [...open].filter((g) => g !== group) : [group]
}

export interface NavMatch {
  group: NavGroup
  key: string
  path: string
  label: string
  icon: string
}

/** Screens whose name, group or description contains every word typed, label matches first. */
export function findScreens(groups: readonly VisibleGroup[], query: string): NavMatch[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (words.length === 0) return []
  const scored: { match: NavMatch; rank: number }[] = []
  for (const g of groups) {
    for (const item of g.items) {
      const label = item.label.toLowerCase()
      const text = `${label} ${g.group.toLowerCase()} ${item.subtitle.toLowerCase()}`
      if (!words.every((w) => text.includes(w))) continue
      const rank = words.every((w) => label.includes(w)) ? 0 : 1
      scored.push({
        rank,
        match: {
          group: g.group,
          key: item.key,
          path: item.path,
          label: item.label,
          icon: item.icon,
        },
      })
    }
  }
  return scored.sort((a, b) => a.rank - b.rank).map((s) => s.match)
}

/** What the browser handed back for the remembered groups, if it is a list of names. */
export function parseRemembered(raw: string | null): string[] {
  if (!raw) return []
  try {
    const value: unknown = JSON.parse(raw)
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
  } catch {
    return []
  }
}
