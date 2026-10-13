import { describe, expect, it } from 'vitest'

import { NO_FIGURE, formatCount, formatDuration, formatPercent, formatSeconds } from './format'

describe('the figures as the deck prints them', () => {
  // Counts from the real May and July reports (aggregates only), divided as the API does.
  it('May: abandon 8.28% and service level 81.1%', () => {
    expect(formatPercent((468 / 5649) * 100, 2)).toBe('8.28%')
    expect(formatPercent((4581 / 5649) * 100, 1)).toBe('81.1%')
  })
  it('July: abandon 4.24% and service level 89.8%', () => {
    expect(formatPercent((205 / 4837) * 100, 2)).toBe('4.24%')
    expect(formatPercent((4344 / 4837) * 100, 1)).toBe('89.8%')
  })
})

describe('formatPercent', () => {
  it('uses the digits it is asked for', () => {
    expect(formatPercent(81.0939, 1)).toBe('81.1%')
    expect(formatPercent(4.2423, 2)).toBe('4.24%')
  })
  it('shows no figure, not 0%, when there is nothing to divide by', () => {
    expect(formatPercent(null)).toBe(NO_FIGURE)
  })
  it('keeps a real zero as a zero', () => {
    expect(formatPercent(0)).toBe('0.0%')
  })
})

describe('formatDuration', () => {
  it.each([
    [215.1, '3:35'], // May AHT on the deck
    [202.2, '3:22'], // July AHT on the deck
    [59.6, '1:00'], // rounds up across the minute, not "0:60"
    [0, '0:00'],
    [3599.4, '59:59'],
    [3661, '1:01:01'],
  ])('%s s is %s', (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text)
  })
  it('shows no figure when there is none', () => {
    expect(formatDuration(null)).toBe(NO_FIGURE)
  })
})

describe('formatSeconds and formatCount', () => {
  it('writes waits to one decimal', () => {
    expect(formatSeconds(18.46)).toBe('18.5 s')
    expect(formatSeconds(11.73)).toBe('11.7 s')
    expect(formatSeconds(null)).toBe(NO_FIGURE)
  })
  it('groups thousands for South African readers', () => {
    expect(formatCount(5649).replace(/\s/g, ' ')).toBe('5 649')
  })
})
