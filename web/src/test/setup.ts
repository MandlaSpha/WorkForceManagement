import '@testing-library/jest-dom/vitest'

import { cleanup, configure } from '@testing-library/vue'
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest'

import { NAV_GROUP_ORDER } from '@/shared/config'

import { backend } from './fake-backend'
import { server } from './server'

// Waiting for a screen to appear is allowed 5 seconds, not the default 1: the suites run side by
// side with the API and end-to-end tests, and a busy machine renders slowly. A test that passes
// does not get slower; only one that would have timed out gets longer to succeed.
configure({ asyncUtilTimeout: 5000 })

// The sidebar starts with every group open here, so the many tests that click a link in the menu
// do not each have to open its group first. The tests of the collapsing itself clear this.
beforeEach(() => {
  localStorage.setItem('wfm.nav.open', JSON.stringify(NAV_GROUP_ORDER))
})

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))

afterEach(() => {
  cleanup()
  server.resetHandlers()
  backend.reset()
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  document.documentElement.classList.remove('dark')
  localStorage.clear()
})

afterAll(() => server.close())
