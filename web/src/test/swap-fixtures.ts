import type { Swap, SwapShift } from '@/entities/swap'

/** Alex (the signed-in agent) is on D1 on Mon 1 Jun 2099; Sam is on L1 the next day. */
export function shiftOf(over: Partial<SwapShift> = {}): SwapShift {
  return {
    assignmentId: 1,
    queueId: 1,
    queue: 'QueueA',
    day: '2099-06-01',
    shift: 'D1',
    startTime: '09:00:00',
    endTime: '17:30:00',
    employeeId: 10,
    employee: 'Alex Agent',
    ...over,
  }
}

export const THEIRS = shiftOf({
  assignmentId: 2,
  day: '2099-06-02',
  shift: 'L1',
  startTime: '13:00:00',
  endTime: '22:00:00',
  employeeId: 11,
  employee: 'Sam Colleague',
})

export function swapOf(over: Partial<Swap> = {}): Swap {
  return {
    id: 1,
    queue: 'QueueA',
    status: 'awaiting_colleague',
    fromEmployee: 'Alex Agent',
    fromDay: '2099-06-01',
    fromShift: 'D1',
    toEmployee: 'Sam Colleague',
    toDay: '2099-06-02',
    toShift: 'L1',
    createdAt: '2026-05-20T08:00:00Z',
    decidedAt: null,
    asker: true,
    colleague: false,
    ...over,
  }
}
