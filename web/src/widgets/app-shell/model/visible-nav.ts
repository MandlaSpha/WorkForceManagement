import { canAccess, type Role } from '@/entities/session'
import { NAV_GROUP_ORDER, NAV_ITEMS, type NavGroup, type NavItem } from '@/shared/config'

export interface VisibleGroup {
  group: NavGroup
  items: NavItem[]
}

/** The sidebar for one role: only screens that role may open, grouped in the standard order,
 * with empty groups dropped. */
export function visibleNav(role: Role): VisibleGroup[] {
  return NAV_GROUP_ORDER.map((group) => ({
    group,
    items: NAV_ITEMS.filter((item) => item.group === group && canAccess(role, item.key)),
  })).filter((g) => g.items.length > 0)
}
