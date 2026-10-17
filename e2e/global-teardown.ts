import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'

/**
 * Every run leaves "E2E Queue ..." queues in the development database. This clears them when the
 * run ends (pass or fail). It only acts on a local Aspire database, never fails the run, and can be
 * turned off with E2E_PURGE=0 (for example to look at what a failed test left behind).
 */
export default function globalTeardown(): void {
  if (process.env.E2E_PURGE === '0') return
  try {
    const out = execFileSync('python', ['-I', resolve(__dirname, '../infra/dev/purge_e2e.py')], {
      encoding: 'utf8',
      timeout: 200_000,
    })
    console.log(out.trim())
  } catch {
    console.log('e2e: could not clear the test queues; use the purge-e2e-data button in Aspire')
  }
}
