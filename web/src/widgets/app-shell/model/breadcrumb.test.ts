import { describe, expect, it } from 'vitest'

import { crumbsFor } from './breadcrumb'
import type { VisibleGroup } from './visible-nav'

const item = (key: string, path: string, label: string) => ({ key, path, label }) as never
const groups: VisibleGroup[] = [
  {
    group: 'Operate',
    items: [item('planner', '/planner', 'Planner'), item('roster', '/roster', 'Roster')],
  },
]

describe('crumbsFor', () => {
  it('names the group and the screen, and links to the first screen of the group', () => {
    // Failure caught: the group crumb leading to the screen you are already on, or to a screen
    // this role may not open.
    expect(crumbsFor(groups, 'roster')).toEqual({
      group: 'Operate',
      groupPath: '/planner',
      title: 'Roster',
    })
  })

  it('has no trail for a screen outside the menu or outside the role', () => {
    expect(crumbsFor(groups, 'audit')).toBeNull()
    expect(crumbsFor([], 'roster')).toBeNull()
  })
})
