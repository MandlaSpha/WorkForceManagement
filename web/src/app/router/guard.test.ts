import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'

import { backend, ACCOUNTS } from '@/test/fake-backend'

import { createAppRouter } from './index'

function newRouter() {
  setActivePinia(createPinia())
  return createAppRouter(createMemoryHistory())
}

async function visit(path: string) {
  const router = newRouter()
  await router.push(path)
  return router.currentRoute.value
}

function signInAs(name: keyof typeof ACCOUNTS) {
  backend.signedIn = ACCOUNTS[name]!.user
}

beforeEach(() => backend.reset())

describe('anonymous visitor', () => {
  it('is sent to the login page, remembering where they wanted to go', async () => {
    const route = await visit('/roster')
    expect(route.name).toBe('login')
    expect(route.query.redirect).toBe('/roster')
  })

  it('may open the login page itself', async () => {
    expect((await visit('/login')).name).toBe('login')
  })
})

describe('signed-in planner', () => {
  it('opens screens the role allows', async () => {
    signInAs('planner')
    expect((await visit('/planner')).name).toBe('planner')
    expect((await visit('/')).name).toBe('dashboard')
  })

  it('is refused admin-only screens with the forbidden page, not a blank one', async () => {
    signInAs('planner')
    expect((await visit('/configure')).name).toBe('forbidden')
    expect((await visit('/audit')).name).toBe('forbidden')
  })

  it('is bounced from the login page to the dashboard', async () => {
    signInAs('planner')
    expect((await visit('/login')).name).toBe('dashboard')
  })
})

describe('signed-in agent', () => {
  it('lands on their own schedule instead of a forbidden dashboard', async () => {
    signInAs('agent')
    expect((await visit('/')).name).toBe('my-schedule')
  })

  it('cannot open planning screens by typing the address', async () => {
    signInAs('agent')
    for (const path of ['/planner', '/roster', '/configure', '/overtime']) {
      expect((await visit(path)).name).toBe('forbidden')
    }
  })

  it('can open their own screens', async () => {
    signInAs('agent')
    expect((await visit('/leave')).name).toBe('leave')
  })
})

describe('signed-in admin', () => {
  it('opens configuration and the audit log', async () => {
    signInAs('admin')
    expect((await visit('/configure')).name).toBe('configure')
    expect((await visit('/audit')).name).toBe('audit')
  })
})

describe('unknown address', () => {
  it('shows not-found to a signed-in user', async () => {
    signInAs('planner')
    expect((await visit('/definitely-not-a-screen')).name).toBe('not-found')
  })
})
