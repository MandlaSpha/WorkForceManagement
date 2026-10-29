import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

/**
 * Every run leaves "E2E Queue ..." queues in the development database. This clears them when the
 * run ends (pass or fail). It only acts on a local Aspire database, never fails the run, and can be
 * turned off with E2E_PURGE=0 (for example to look at what a failed test left behind).
 */
export default function globalTeardown(): void {
  if (process.env.E2E_PURGE === '0') return
  try {
    const out = execFileSync(
      'python',
      ['-I', fileURLToPath(new URL('../infra/dev/purge_e2e.py', import.meta.url))],
      {
        encoding: 'utf8',
        timeout: 200_000,
      },
    )
    console.log(out.trim())
  } catch (problem) {
    const why = problem instanceof Error ? (problem.message.split('\n')[0] ?? '') : 'unknown'
    console.log(`e2e: could not clear the test queues (${why}); use the purge button in Aspire`)
  }
}
