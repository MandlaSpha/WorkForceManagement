import { canOpen, type SessionUser } from '@/entities/session'
import { NAV_GROUP_ORDER, NAV_ITEMS, type NavGroup, type NavItem } from '@/shared/config'

export interface VisibleGroup {
  group: NavGroup
  items: NavItem[]
}

/** The sidebar for one person: only screens their role may open AND whose feature is on, grouped in the standard order,
 * with empty groups dropped. */
export function visibleNav(user: Pick<SessionUser, 'role' | 'features'>): VisibleGroup[] {
  return NAV_GROUP_ORDER.map((group) => ({
    group,
    items: NAV_ITEMS.filter((item) => item.group === group && canOpen(user, item.key)),
  })).filter((g) => g.items.length > 0)
}
