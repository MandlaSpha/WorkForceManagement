import { useMutation } from '@tanstack/vue-query'

import { runScenario, type ScenarioRequest } from '@/entities/forecast'

/** A what-if only asks; it changes nothing on the server, so no cache needs refreshing. */
export function useRunScenario() {
  return useMutation({ mutationFn: (body: ScenarioRequest) => runScenario(body) })
}
