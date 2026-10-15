/** Why a row of an employee file was not kept, in words a planner can act on. */
const IMPORT_REASON: Record<string, string> = {
  emp_no_invalid: 'no employee number, or one longer than 20 characters',
  name_missing: 'no name for a new person',
  duplicate_in_file: 'an employee number that is in the file twice (the second is skipped)',
  contract_invalid: 'a contract that is not permanent or seasonal',
  work_mode_invalid: 'a work mode that is not office, remote or hybrid',
  hours_invalid: 'weekly hours that are not a number above 0 and at most 60',
  date_invalid: 'a date that is not yyyy-mm-dd or dd/mm/yyyy',
  dates_invalid: 'an end date before the start date',
  queue_unknown: 'a queue that does not exist (queues come from imported call data)',
  skill_level_invalid: 'a skill level that is not 1, 2 or 3',
  queue_repeated: 'the same queue listed twice',
  manager_unknown: 'a manager who is not an employee yet',
  manager_self: 'someone named as their own manager',
  manager_cannot: 'a manager who has no login that can approve leave',
  login_taken: 'an ACD login that already belongs to somebody else',
}

export function importReason(code: string): string {
  return IMPORT_REASON[code] ?? code
}
