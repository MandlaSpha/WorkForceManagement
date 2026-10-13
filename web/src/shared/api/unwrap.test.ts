import { describe, expect, it } from 'vitest'

import { ApiProblem } from './problem'
import { unwrap } from './unwrap'

describe('unwrap', () => {
  it('returns the data of a successful call', () => {
    expect(unwrap({ data: { ok: true }, response: new Response() })).toEqual({ ok: true })
  })

  it('keeps falsy data (an empty list is a real answer, not a failure)', () => {
    expect(unwrap({ data: [], response: new Response() })).toEqual([])
    expect(unwrap({ data: 0, response: new Response() })).toBe(0)
  })

  it('turns an API problem into an ApiProblem with its stable code and detail', () => {
    const response = new Response(null, { status: 409 })
    const error = { code: 'import.duplicate_period', title: 'Period already imported', detail: 'x' }
    try {
      unwrap({ error, response })
      expect.unreachable()
    } catch (caught) {
      expect(caught).toBeInstanceOf(ApiProblem)
      expect((caught as ApiProblem).status).toBe(409)
      expect((caught as ApiProblem).code).toBe('import.duplicate_period')
      expect((caught as ApiProblem).detail).toBe('x')
    }
  })

  it('still throws when the server sent no problem body at all', () => {
    expect(() => unwrap({ response: new Response(null, { status: 502 }) })).toThrow(ApiProblem)
  })
})
