import type { components } from '@/shared/api'

export type ForecastJob = components['schemas']['JobOut']
export type ForecastVersion = components['schemas']['ForecastVersionOut']
export type ForecastInterval = components['schemas']['ForecastIntervalOut']
export type ForecastAccuracy = components['schemas']['AccuracyOut']
export type ForecastEvent = components['schemas']['EventOut']
export type EventRequest = components['schemas']['EventIn']
export type ScenarioRequest = components['schemas']['ScenarioIn']
export type ScenarioResult = components['schemas']['ScenarioOut']
export type ScenarioDay = components['schemas']['ScenarioDayOut']
export type Tuning = components['schemas']['TuningOut']
export type TuningRequest = components['schemas']['TuningIn']
export type Backtest = components['schemas']['BacktestOut']
export type Score = components['schemas']['ScoreOut']
export type RunForecastRequest = components['schemas']['RunForecastIn']
/** The models whose past accuracy can be compared (Prophet is slow, so it is not one of them). */
export type ForecastMethod = 'baseline' | 'smoothed'
export type ForecastRange = components['schemas']['RangeOut']
export type RangeDay = components['schemas']['RangeDayOut']
export type LifecycleRequest = components['schemas']['LifecycleIn']
