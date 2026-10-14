import ExcelJS from 'exceljs'

/**
 * Builds a tiny, made-up ACD Call Detail Report for the browser tests: fake queue, fake call IDs,
 * a fake phone number and agent name, no real people. Shared by the import and forecast specs.
 */
export const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

const HEADERS = [
  'Call ID',
  'Phone Number',
  'Call Type',
  'Queue',
  'Agent',
  'Start Time',
  'Queue Time',
  'Agent Time',
  'Hangup Time',
  'Call Duration',
  'Agent Duration',
  'Queue Wait Time',
  'Call Status',
  'Hangup By',
  'Total Hold Duration',
  'Disposition Duration',
]

export interface Call {
  type: 'INBOUND' | 'OUTBOUND'
  status: 'Agent' | 'Abandoned' | 'Dial'
  clock: string // local time the call started, "10:05:00"
  wait: number
  talk: number
  wrap: number
}

export const hms = (seconds: number) =>
  [Math.floor(seconds / 3600), Math.floor((seconds % 3600) / 60), seconds % 60]
    .map((n) => String(n).padStart(2, '0'))
    .join(':')

export const rand = (below: number) => Math.floor(Math.random() * below)

/** A call ID block no real report uses, different on every run. */
export const randomFirstId = () => 9_000_000_000 + rand(900_000_000)

/** A Monday somewhere in 2003 to 2020: far from real data, and the weekday the forecast needs. */
export function randomMonday(): string {
  const day = new Date(Date.UTC(2003 + rand(18), rand(12), 1 + rand(27)))
  day.setUTCDate(day.getUTCDate() + ((1 - day.getUTCDay() + 7) % 7))
  return day.toISOString().slice(0, 10)
}

export function addDays(date: string, days: number): string {
  const day = new Date(`${date}T00:00:00Z`)
  day.setUTCDate(day.getUTCDate() + days)
  return day.toISOString().slice(0, 10)
}

export async function buildReport(options: {
  date: string // YYYY-MM-DD
  firstId: number
  calls: Call[]
  queue: string
}): Promise<Buffer> {
  const book = new ExcelJS.Workbook()
  const sheet = book.addWorksheet('Call Record Report')
  sheet.addRow(HEADERS)
  options.calls.forEach((call, index) => {
    const answered = call.status === 'Agent'
    const start = `${options.date} ${call.clock}`
    const row: Record<string, string | number | null> = {
      'Call ID': options.firstId + index,
      'Phone Number': '27000000000', // fake, and never stored
      'Call Type': call.type,
      Queue: options.queue,
      Agent: answered ? 'Test Person (Agent900)' : null,
      'Start Time': start,
      'Queue Time': start,
      'Agent Time': answered ? start : '0000-00-00 00:00:00',
      'Hangup Time': start,
      'Call Duration': hms(call.wait + call.talk),
      'Agent Duration': hms(call.talk),
      'Queue Wait Time': hms(call.wait),
      'Call Status': call.status,
      'Hangup By': 'USER',
      'Total Hold Duration': hms(0),
      'Disposition Duration': hms(call.wrap),
    }
    sheet.addRow(HEADERS.map((name) => row[name] ?? null))
  })
  return Buffer.from(await book.xlsx.writeBuffer())
}

/** Ten answered calls in the 10:00 half-hour. The importer refuses a second file with the same
 * first call, last call and row count, so the first call's second is random: every run's file is
 * its own (the half-hour, and so the hand-worked numbers, do not change). */
export function tenCalls(): Call[] {
  const seconds = String(1 + rand(59)).padStart(2, '0') // never :00, which earlier runs used
  return Array.from({ length: 10 }, (_, i) => ({
    type: 'INBOUND',
    status: 'Agent',
    clock: `10:0${i}:${i === 0 ? seconds : '00'}`,
    wait: 0,
    talk: 150,
    wrap: 30,
  }))
}
