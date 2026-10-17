import { ApiProblem, api, unwrap } from '@/shared/api'

import type { Job } from '../model/types'

export async function fetchJob(jobId: string): Promise<Job> {
  return unwrap(await api.GET('/api/v1/jobs/{job_id}', { params: { path: { job_id: jobId } } }))
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** Ask how a background job is getting on until it is done, and return it. A job that failed
 * throws the same problem a refused click would, so screens show it the same way. The wait ends
 * with a plain error if the worker never answers. */
export async function waitForJob(
  started: Job,
  { everyMs = 1000, giveUpMs = 10 * 60 * 1000, wait = sleep } = {},
): Promise<Job> {
  let job = started
  for (let waited = 0; ; waited += everyMs) {
    if (job.status === 'done') return job
    if (job.status === 'failed') {
      throw new ApiProblem({
        status: 409,
        code: job.errorCode,
        title: 'The job failed',
        detail: job.errorDetail,
      })
    }
    if (waited >= giveUpMs) {
      throw new ApiProblem({
        status: 504,
        code: 'job.timeout',
        title: 'The job is taking too long',
        detail: 'It is still running. Check back in a few minutes before trying again.',
      })
    }
    await wait(everyMs)
    job = await fetchJob(started.id)
  }
}
