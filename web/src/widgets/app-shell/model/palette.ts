import { ref } from 'vue'

import { canOpen, type SessionUser } from '@/entities/session'
import type { NavKey } from '@/shared/config'

import { allScreens, findScreens } from './nav-state'
import type { VisibleGroup } from './visible-nav'

/** One row of the command palette. Only places to go: the palette never writes anything. */
export interface PaletteItem {
  id: string
  kind: 'page' | 'queue' | 'action'
  label: string
  hint: string
  icon: string
  /** Where Enter takes you. */
  to: string
  /** For a queue row: the queue to select in the top bar first. */
  queueId?: number
}

export interface PaletteGroup {
  title: 'Pages' | 'Queues' | 'Actions'
  items: PaletteItem[]
}

/** Shared open flag, so the sidebar button and the keyboard shortcut drive the same panel. */
export const paletteOpen = ref(false)

type Viewer = Pick<SessionUser, 'role' | 'features'>

interface ActionDef {
  id: string
  label: string
  hint: string
  icon: string
  to: string
  /** The screen that must be open to this person for the action to make sense. */
  needs: NavKey
}

/** Shortcuts to things that already exist. "Request leave" opens the same form as the Leave
 * page's button; nothing here changes data on its own. */
const ACTIONS: readonly ActionDef[] = [
  {
    id: 'request-leave',
    label: 'Request leave',
    hint: 'Opens the leave request form',
    icon: 'calendar',
    to: '/leave?new=1',
    needs: 'leave',
  },
  {
    id: 'open-planner',
    label: 'Open planner',
    hint: 'Coverage against requirement',
    icon: 'layout-grid',
    to: '/planner',
    needs: 'planner',
  },
  {
    id: 'swap-shift',
    label: 'Swap a shift',
    hint: 'Offer a shift to a colleague',
    icon: 'arrow-left-right',
    to: '/shift-swaps',
    needs: 'swaps',
  },
]

/** The queues rows may lead to the planner (or the dashboard); a role with neither sees none. */
export function queueTarget(user: Viewer): string | null {
  if (canOpen(user, 'planner')) return '/planner'
  if (canOpen(user, 'dashboard')) return '/'
  return null
}

const words = (q: string): string[] => q.toLowerCase().split(/\s+/).filter(Boolean)

/**
 * What the palette shows for what was typed. Filtering is entirely local: the typed text goes
 * nowhere. People are deliberately not searchable here (privacy); pages, queues and actions are.
 */
export function buildPalette(input: {
  user: Viewer
  nav: readonly VisibleGroup[]
  queues: readonly { id: number; name: string }[]
  query: string
}): PaletteGroup[] {
  const { user, nav, queues, query } = input
  const w = words(query)

  const pages = (w.length === 0 ? allScreens(nav) : findScreens(nav, query)).map<PaletteItem>(
    (m) => ({
      id: `page-${m.key}`,
      kind: 'page',
      label: m.label,
      hint: m.subtitle || 'Go to page',
      icon: m.icon,
      to: m.path,
    }),
  )

  const target = queueTarget(user)
  const queueRows: PaletteItem[] =
    target === null
      ? []
      : queues
          .filter((q) => w.every((x) => q.name.toLowerCase().includes(x)))
          .map((q) => ({
            id: `queue-${q.id}`,
            kind: 'queue' as const,
            label: q.name,
            hint: 'Show this queue',
            icon: 'layers',
            to: target,
            queueId: q.id,
          }))

  const actions = ACTIONS.filter((a) => canOpen(user, a.needs))
    .filter((a) => w.every((x) => `${a.label} ${a.hint}`.toLowerCase().includes(x)))
    .map<PaletteItem>((a) => ({ ...a, id: `action-${a.id}`, kind: 'action' }))

  // Few queues are listed before anything is typed; a long list would bury the pages.
  const shownQueues = w.length === 0 ? queueRows.slice(0, 5) : queueRows
  const out: PaletteGroup[] = [
    { title: 'Pages', items: pages },
    { title: 'Queues', items: shownQueues },
    { title: 'Actions', items: actions },
  ]
  return out.filter((g) => g.items.length > 0)
}

/** Keep the highlighted row inside the list after it changes length. */
export function clampIndex(index: number, length: number): number {
  if (length <= 0) return 0
  return Math.min(Math.max(index, 0), length - 1)
}
