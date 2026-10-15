import type { BoardEntry, Swap, SwapShift } from '@/entities/swap'

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

/** A request another agent posted, as the board shows it: no name. */
export function boardOf(over: Partial<BoardEntry> = {}): BoardEntry {
  return {
    id: 5,
    queue: 'QueueA',
    day: '2099-06-02',
    shift: 'L1',
    startTime: '13:00:00',
    endTime: '22:00:00',
    createdAt: '2026-05-20T08:00:00Z',
    ...over,
  }
}

export function swapOf(over: Partial<Swap> = {}): Swap {
  return {
    id: 1,
    queue: 'QueueA',
    status: 'open',
    fromEmployee: 'Alex Agent',
    fromDay: '2099-06-01',
    fromShift: 'D1',
    toEmployee: null,
    toDay: null,
    toShift: null,
    createdAt: '2026-05-20T08:00:00Z',
    decidedAt: null,
    asker: true,
    colleague: false,
    ...over,
  }
}

/** A swap that has been taken and waits for a lead. */
export function matchedOf(over: Partial<Swap> = {}): Swap {
  return swapOf({
    status: 'awaiting_approval',
    toEmployee: 'Sam Colleague',
    toDay: '2099-06-02',
    toShift: 'L1',
    ...over,
  })
}
