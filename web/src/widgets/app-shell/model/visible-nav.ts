import { canOpen, type SessionUser } from '@/entities/session'
import { NAV_GROUP_ORDER, NAV_ITEMS, type NavGroup, type NavItem } from '@/shared/config'

export interface VisibleGroup {
  group: NavGroup
  items: NavItem[]
}

type Viewer = Pick<SessionUser, 'role' | 'features'>

/** The sidebar for one person: only screens their role may open AND whose feature is on, grouped in the standard order,
 * with empty groups dropped. */
export function visibleNav(user: Viewer): VisibleGroup[] {
  return NAV_GROUP_ORDER.map((group) => ({
    group,
    items: NAV_ITEMS.filter((item) => item.group === group && canOpen(user, item.key)),
  })).filter((g) => g.items.length > 0)
}

/** The Admin group is drawn under "Settings" at the foot of the sidebar, not in the main list. */
export const SETTINGS_GROUP: NavGroup = 'Admin'

/** The main list: everything except the settings group, so no screen appears twice. */
export function mainNav(user: Viewer): VisibleGroup[] {
  return visibleNav(user).filter((g) => g.group !== SETTINGS_GROUP)
}

/** The settings screens this person may open. */
export function settingsItems(user: Viewer): NavItem[] {
  return visibleNav(user).find((g) => g.group === SETTINGS_GROUP)?.items ?? []
}
