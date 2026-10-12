import { setupServer } from 'msw/node'

import { handlers } from './fake-backend'

/** The single MSW server for a test file. Tests add per-test overrides with server.use(...). */
export const server = setupServer(...handlers)
