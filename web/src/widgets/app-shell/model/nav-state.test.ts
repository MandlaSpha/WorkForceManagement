import { describe, expect, it } from 'vitest'

import { activeGroup, afterClick, findScreens, openGroups, parseRemembered } from './nav-state'
import type { VisibleGroup } from './visible-nav'

const item = (key: string, path: string, label: string, subtitle = '') =>
  ({ key, path, label, subtitle, icon: 'calendar' }) as never

const groups: VisibleGroup[] = [
  {
    group: 'Operate',
    items: [
      item('roster', '/roster', 'Roster', 'Who works when'),
      item('swaps', '/swaps', 'Swaps'),
    ],
  },
  {
    group: 'People',
    items: [item('leave', '/leave', 'Leave', 'Annual leave requests')],
  },
  { group: 'Admin', items: [item('users', '/users', 'Users')] },
]

describe('which groups the sidebar shows open', () => {
  it('opens the group you are in when none was chosen', () => {
    // Failure caught: the sidebar hiding the screen you are looking at.
    expect(activeGroup(groups, '/leave')).toBe('People')
    expect([...openGroups(groups, '/leave', [])]).toEqual(['People'])
  })

  it('shows what the person chose instead of the group they are in', () => {
    expect([...openGroups(groups, '/leave', ['Operate'])]).toEqual(['Operate'])
  })

  it('ignores remembered names that are no longer groups', () => {
    // Failure caught: a renamed group leaving a ghost entry that opens nothing, or throws.
    expect([...openGroups(groups, '/nowhere', ['Gone'])]).toEqual([])
  })

  it('treats a sub-path as being in the group', () => {
    expect(activeGroup(groups, '/swaps/12')).toBe('Operate')
  })
})

describe('clicking a group', () => {
  it('opens it and closes the others, so the menu never grows into a long list', () => {
    // Failure caught: groups piling up open until the menu needs a scrollbar again.
    expect(afterClick(new Set(['Operate']), 'Insight')).toEqual(['Insight'])
    expect(afterClick(new Set(['Operate', 'People']), 'Admin')).toEqual(['Admin'])
  })

  it('closes the one that is open when clicked again', () => {
    expect(afterClick(new Set(['Operate']), 'Operate')).toEqual([])
  })
})

describe('finding a screen', () => {
  it('matches by name, case-insensitively, and by what the screen is about', () => {
    expect(findScreens(groups, 'ROSTER').map((m) => m.key)).toEqual(['roster'])
    expect(findScreens(groups, 'annual').map((m) => m.key)).toEqual(['leave'])
  })

  it('needs every word, and ranks a name match above a description match', () => {
    // Failure caught: "leave" listing a screen that only mentions leave in passing before Leave.
    const g: VisibleGroup[] = [
      { group: 'Operate', items: [item('a', '/a', 'Planner', 'Plan around leave')] },
      { group: 'People', items: [item('b', '/b', 'Leave', '')] },
    ]
    expect(findScreens(g, 'leave').map((m) => m.key)).toEqual(['b', 'a'])
    expect(findScreens(groups, 'leave requests').map((m) => m.key)).toEqual(['leave'])
    expect(findScreens(groups, 'leave zzz')).toEqual([])
  })

  it('finds nothing for an empty search, rather than everything', () => {
    expect(findScreens(groups, '   ')).toEqual([])
  })

  it('only searches screens the person may open', () => {
    // The groups passed in are already the person's own; an agent's list has no Users screen.
    const agent = groups.filter((g) => g.group !== 'Admin')
    expect(findScreens(agent, 'users')).toEqual([])
  })
})

describe('what was remembered', () => {
  it('reads a list of names and shrugs off anything else', () => {
    expect(parseRemembered('["Operate","People"]')).toEqual(['Operate', 'People'])
    expect(parseRemembered('{"a":1}')).toEqual([])
    expect(parseRemembered('not json')).toEqual([])
    expect(parseRemembered(null)).toEqual([])
    expect(parseRemembered('["Operate",3]')).toEqual(['Operate'])
  })
})
