# ADR 0002: Prophet forecasts day totals; the baseline stays as the fallback

Status: Accepted, 14 October 2026

## Context
Forecasting is the highest-scoring WFM item in the tender (1.0 of 3.0 points) and asks for "predictive forecasting for future demand". Our baseline (weighted average of recent same-weekday days) has no trend, holidays or month-end effects and scores 43-72% on day totals for the real queues (tech spec 4.3). Only about two months of real calls exist today.

## Options considered
1. **Improve the baseline by hand** (trend factor, smoothing). Cheap, but every effect (holidays, month-end, trend) is then our own code to get right and test.
2. **Prophet** (chosen): additive model with trend, weekly and yearly seasonality and holiday effects, widely used for exactly this; gives an uncertainty band.
3. **Gradient boosting / other ML.** Needs far more history than we have; kept as FC-07 for later, judged against the same backtest.

## Decision
- Prophet forecasts **daily totals** only. The existing intraday profile spreads a total over the 48 half-hours (`wfm_engine.forecast.spread_day_total`), so staffing, publishing, audit and the roster plan are unchanged.
- It sits in the API layer (`wfm/forecasting/prophet_model.py`), not in `wfm_engine`, which stays free of Django, the clock and I/O and of heavy dependencies.
- **Prophet must earn its place.** A rolling-origin backtest (refit each week on only the days before it) scores Prophet and the baseline on the same days. The version uses Prophet only if its day-total accuracy is strictly higher; otherwise it uses the baseline and records why (`params.fallback`). With too little history it also falls back. The screen says which model produced a forecast.
- Yearly seasonality is switched on only with two years of history and monthly seasonality only with three months; the switches used are stored with the version so a forecast can be explained and reproduced.
- **Multiplicative seasonality.** Weekday and holiday effects scale with the level of the queue. On a synthetic growing queue whose true day total is known by hand (536), additive seasonality gave 499 (7% low) and multiplicative gave 536; the test keeps it honest.
- Days without data are missing rows for Prophet, never zeros (DAT-10).

## Consequences
- Dependencies added: prophet (MIT), cmdstanpy (BSD-3), holidays (MIT), pandas (BSD-3), numpy (BSD-3), matplotlib (PSF-based, a Prophet requirement), plus their small transitive libraries. All permissive and open source.
- **No compiler or cmdstan build is needed**: the Prophet 1.5 wheel ships the compiled model for Windows and Linux; verified on the Windows development machine. The worker image must use a glibc Python base (not Alpine/musl).
- A fit takes about a second. A run with its backtest (at most the last six weekly origins) stays inside a request for now; it moves to the Celery worker behind the job API when runs grow.
- Forecast accuracy is reported per model so the comparison is visible, not asserted.
