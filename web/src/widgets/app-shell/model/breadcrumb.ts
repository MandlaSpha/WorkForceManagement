import type { VisibleGroup } from './visible-nav'

export interface Crumbs {
  group: string
  /** The first screen of the group that this person may open: where the group crumb leads. */
  groupPath: string
  title: string
}

/** "<group> > <screen>" for the screen with this route name, or null for a screen not in the menu
 * (a 404, sign-in). The groups passed in are the person's own, so the link never leads somewhere
 * they may not go. */
export function crumbsFor(groups: readonly VisibleGroup[], key: string): Crumbs | null {
  for (const g of groups) {
    const item = g.items.find((i) => i.key === key)
    const first = g.items[0]
    if (item && first) return { group: g.group, groupPath: first.path, title: item.label }
  }
  return null
}
