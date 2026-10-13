/** Plain-language versions of the importer's reason codes. The codes never contain cell values. */
const REASONS: Record<string, string> = {
  'queue_wait.negative': 'a negative queue wait (the call was kept, the wait ignored)',
  'queue_wait.unreadable': 'an unreadable queue wait (the call was kept, the wait ignored)',
  'agent_duration.unreadable': 'an unreadable talk time (the call was kept, the time ignored)',
  'disposition.unreadable': 'an unreadable wrap-up time (the call was kept, the time ignored)',
  'hold.unreadable': 'an unreadable hold time (the call was kept, the time ignored)',
  'call_duration.unreadable': 'an unreadable call length (the call was kept, the length ignored)',
  'hangup_time.unreadable': 'an unreadable hang-up time (the call was kept, the time ignored)',
  'queue_time.unreadable': 'an unreadable queue time (the call was kept, the time ignored)',
  'agent_time.unreadable': 'an unreadable agent time (the call was kept, the time ignored)',
  'call_id.missing': 'no call ID (the row was skipped)',
  'call_id.unreadable': 'a call ID that is not a number (the row was skipped)',
  'call_type.missing': 'no call type (the row was skipped)',
  'queue.missing': 'no queue (the row was skipped)',
  'status.missing': 'no call status (the row was skipped)',
  'start_time.missing': 'no start time (the row was skipped)',
  'timestamp.unreadable': 'a start time that cannot be read (the row was skipped)',
}

export function describeReason(code: string): string {
  return REASONS[code] ?? `a problem the importer reports as "${code}"`
}
