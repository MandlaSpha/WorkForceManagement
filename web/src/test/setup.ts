import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/vue'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { backend } from './fake-backend'
import { server } from './server'

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
