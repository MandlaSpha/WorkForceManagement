import { describe, expect, it, vi } from 'vitest'

import { ApiProblem } from '@/shared/api'

import type { Job } from '../model/types'
import { waitForJob } from './job'

const job = (over: Partial<Job> = {}): Job => ({
  id: 'j1',
  kind: 'auto_schedule',
  status: 'queued',
  result: null,
  errorCode: '',
  errorDetail: '',
  createdAt: '2031-03-01T08:00:00Z',
  finishedAt: null,
  ...over,
})

function answers(...statuses: Array<Partial<Job>>) {
  const queue = [...statuses]
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async () =>
      new Response(JSON.stringify(job(queue.shift() ?? { status: 'running' })), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
}

describe('waitForJob', () => {
  it('asks until the job is done and returns its result', async () => {
    answers({ status: 'running' }, { status: 'done', result: { placed: 2 } })
    const wait = vi.fn(async () => {})
    const finished = await waitForJob(job(), { wait })
    expect(finished.result).toEqual({ placed: 2 })
    expect(wait).toHaveBeenCalledTimes(2)
  })

  it('does not ask at all for a job that is already done', async () => {
    const spy = vi.spyOn(globalThis, 'fetch')
    await waitForJob(job({ status: 'done' }), { wait: async () => {} })
    expect(spy).not.toHaveBeenCalled()
  })

  it('throws the failure as a problem a screen can show, with the job code', async () => {
    // Failure caught: a failed job reported as success, or its reason lost.
    answers({ status: 'failed', errorCode: 'autoschedule.published', errorDetail: 'Published.' })
    await expect(waitForJob(job(), { wait: async () => {} })).rejects.toMatchObject({
      code: 'autoschedule.published',
      detail: 'Published.',
    })
  })

  it('gives up with a plain message instead of waiting for ever', async () => {
    // Failure caught: a screen stuck on "Running…" when the worker is down.
    answers({ status: 'queued' }, { status: 'queued' }, { status: 'queued' })
    const error = await waitForJob(job(), {
      everyMs: 10,
      giveUpMs: 20,
      wait: async () => {},
    }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiProblem)
    expect(error).toMatchObject({ code: 'job.timeout' })
  })
})
