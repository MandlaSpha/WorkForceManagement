import { NAV_ITEMS, type FeatureKey, type NavKey } from '@/shared/config'

export const ROLES = ['agent', 'lead', 'planner', 'admin', 'executive', 'customer_ops'] as const
export type Role = (typeof ROLES)[number]

export function isRole(value: unknown): value is Role {
  return typeof value === 'string' && (ROLES as readonly string[]).includes(value)
}

export const ROLE_LABELS: Record<Role, string> = {
  agent: 'Agent',
  lead: 'Team lead',
  planner: 'Planner',
  admin: 'Admin',
  executive: 'Executive',
  customer_ops: 'Customer operations',
}

/**
 * Which roles may open which screen (role matrix, docs/04-UML.md section 2.6).
 *
 * This only decides what the UI shows. The API is the authority and refuses anything a role may
 * not do, so hiding a link here is cosmetic, never the protection.
 */
export const ACCESS: Record<NavKey, readonly Role[]> = {
  dashboard: ['planner', 'lead', 'admin', 'executive', 'customer_ops'],

  'my-schedule': ['agent'],
  'my-availability': ['agent'],

  planner: ['planner', 'lead', 'admin'],
  intraday: ['planner', 'lead', 'admin'],
  roster: ['planner', 'lead', 'admin'],
  forecast: ['planner', 'lead', 'admin'],
  recommendations: ['planner', 'admin'],
  capacity: ['planner', 'admin', 'executive', 'customer_ops'],
  scheduling: ['planner', 'lead', 'admin'],
  imports: ['planner', 'admin'],
  'service-desk': ['planner', 'admin', 'customer_ops'],

  leave: ['agent', 'lead', 'planner', 'admin'],
  swaps: ['agent', 'lead', 'planner', 'admin'],
  employees: ['planner', 'lead', 'admin'],
  overtime: ['lead', 'planner', 'admin'],
  attendance: ['lead', 'planner', 'admin'],

  analytics: ['planner', 'admin', 'executive', 'customer_ops'],
  calibration: ['planner', 'admin'],
  reports: ['planner', 'lead', 'admin', 'executive', 'customer_ops'],

  configure: ['admin'],
  audit: ['admin'],
}

export function canAccess(role: Role, key: NavKey): boolean {
  return ACCESS[key].includes(role)
}

/** Is the screen's feature switched on? Screens of the `core` feature always are. */
export function isAvailable(features: ReadonlyArray<FeatureKey>, key: NavKey): boolean {
  const feature = NAV_ITEMS.find((item) => item.key === key)?.feature
  return feature === undefined || feature === 'core' || features.includes(feature)
}

/** May this person open the screen: the role allows it AND the feature is on. */
export function canOpen(
  user: { role: Role; features: ReadonlyArray<FeatureKey> },
  key: NavKey,
): boolean {
  return canAccess(user.role, key) && isAvailable(user.features, key)
}

/** Where a role lands after signing in: agents get their own schedule, everyone else the dashboard. */
export function homePathFor(role: Role): string {
  return role === 'agent' ? '/my-schedule' : '/'
}
