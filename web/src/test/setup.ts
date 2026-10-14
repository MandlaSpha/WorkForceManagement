import '@testing-library/jest-dom/vitest'

import { cleanup, configure } from '@testing-library/vue'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { backend } from './fake-backend'
import { server } from './server'

// Waiting for a screen to appear is allowed 5 seconds, not the default 1: the suites run side by
// side with the API and end-to-end tests, and a busy machine renders slowly. A test that passes
// does not get slower; only one that would have timed out gets longer to succeed.
configure({ asyncUtilTimeout: 5000 })

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
