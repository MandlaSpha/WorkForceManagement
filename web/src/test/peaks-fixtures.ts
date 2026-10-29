import type { Peaks } from '@/entities/peaks'

/** Synthetic: two Mondays (40 and 50 calls) and a Tuesday (20), three half-hours with calls. */
export const peaksOf = (over: Partial<Peaks> = {}): Peaks => ({
  queueId: 1,
  dateFrom: '2031-03-01',
  dateTo: '2031-03-14',
  daysMeasured: 3,
  busiestDays: [
    { day: '2031-03-10', offered: 50 },
    { day: '2031-03-03', offered: 40 },
  ],
  quietestDays: [
    { day: '2031-03-04', offered: 20 },
    { day: '2031-03-03', offered: 40 },
  ],
  busiestIntervals: [{ start: '2031-03-03 10:30', offered: 36 }],
  busiestSlots: [
    { slot: '10:30', averageOffered: '35.8', days: 3 },
    { slot: '08:00', averageOffered: '25.0', days: 2 },
  ],
  quietestSlots: [
    { slot: '08:30', averageOffered: '5.0', days: 1 },
    { slot: '08:00', averageOffered: '25.0', days: 2 },
  ],
  daily: [
    { day: '2031-03-03', offered: 40 },
    { day: '2031-03-04', offered: 20 },
    { day: '2031-03-10', offered: 50 },
  ],
  profile: [
    { slot: '08:00', averageOffered: '25.0', days: 2 },
    { slot: '08:30', averageOffered: '5.0', days: 1 },
    { slot: '10:30', averageOffered: '35.8', days: 3 },
  ],
  heat: [
    { weekday: 0, slot: 16, averageOffered: '25.0', days: 2 },
    { weekday: 0, slot: 21, averageOffered: '40.0', days: 2 },
    { weekday: 1, slot: 17, averageOffered: '5.0', days: 1 },
  ],
  ...over,
})
