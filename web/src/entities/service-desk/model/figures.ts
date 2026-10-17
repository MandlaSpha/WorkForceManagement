/** Required people with two decimals: 0.9 is "0.90". A minimum is marked "at least". */
export function fteLabel(fte: number | null, complete = true): string {
  if (fte === null) return '\u2014'
  return `${complete ? '' : 'at least '}${fte.toFixed(2)}`
}

/** The reasons a row of a work-item file was not kept, in words. */
export const REJECT_REASON: Record<string, string> = {
  bad_ref: 'no usable reference',
  bad_pool: 'no pool',
  bad_opened: 'an opened time that could not be read',
  bad_date: 'a deadline or closed time that could not be read',
  bad_effort: 'an effort that is not a whole number of minutes',
  repeated_ref: 'a reference that appears twice in the file',
  closed_before_opened: 'a closed time before the opened time',
  bad_fcr: 'a first-contact answer that is not yes or no',
  bad_csat: 'a CSAT that is not a whole number from 1 to 5',
  bad_nps: 'an NPS that is not a whole number from 0 to 10',
}

export function rejectReason(code: string): string {
  return REJECT_REASON[code] ?? code
}
