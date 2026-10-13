import { toProblem } from './problem'

/**
 * The data of an openapi-fetch result, or an `ApiProblem` thrown for anything else. One place that
 * decides what "the call failed" means, so every screen reports API errors the same way.
 */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) throw toProblem(result.error, result.response)
  return result.data
}
