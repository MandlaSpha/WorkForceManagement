import type { components } from '@/shared/api'

export type ForecastVersion = components['schemas']['ForecastVersionOut']
export type ForecastInterval = components['schemas']['ForecastIntervalOut']
export type ForecastAccuracy = components['schemas']['AccuracyOut']
export type ForecastEvent = components['schemas']['EventOut']
export type EventRequest = components['schemas']['EventIn']
export type RunForecastRequest = components['schemas']['RunForecastIn']
