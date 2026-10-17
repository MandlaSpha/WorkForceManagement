import type { ImportReport, KpiSummary, QueueKpis } from '@/entities/call-data'

export const metric = (value: number | null, used = 1100, total = 1488) => ({
  value,
  basis: 'measured' as const,
  coverage: { intervalsUsed: used, intervalsTotal: total },
})

/** Service figures for one queue, with the real May totals as the default (aggregates only). */
export function queueKpis(overrides: Partial<QueueKpis> = {}): QueueKpis {
  return {
    queueId: 1,
    queue: 'QueueA',
    confirmed: true,
    offered: 5649,
    answered: 5181,
    abandoned: 468,
    abandonPct: metric((468 / 5649) * 100),
    serviceLevelPct: metric((4581 / 5649) * 100),
    asaS: metric(18.46),
    ahtS: metric(215.1),
    ...overrides,
  }
}

export function kpiSummary(overrides: Partial<KpiSummary> = {}): KpiSummary {
  return {
    dateFrom: '2026-05-01',
    dateTo: '2026-05-31',
    slThresholdS: 20,
    total: queueKpis({ queueId: null, queue: 'All queues' }),
    queues: [
      queueKpis(),
      queueKpis({ queueId: 2, queue: 'QueueB', offered: 10, confirmed: false }),
    ],
    ...overrides,
  }
}

export function emptySummary(): KpiSummary {
  const none = queueKpis({
    offered: 0,
    answered: 0,
    abandoned: 0,
    abandonPct: metric(null, 0),
    serviceLevelPct: metric(null, 0),
    asaS: metric(null, 0),
    ahtS: metric(null, 0),
  })
  return kpiSummary({ total: none, queues: [none] })
}

export function importReport(overrides: Partial<ImportReport> = {}): ImportReport {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    fileName: 'may.xlsx',
    createdAt: '2026-10-13T10:00:00Z',
    uploadedBy: 'Pat Planner',
    sourceTimezone: 'Africa/Johannesburg',
    periodStart: '2026-04-30T22:00:00Z',
    periodEnd: '2026-05-31T21:00:00Z',
    rowsRead: 5971,
    rowsInserted: 5971,
    rowsDuplicate: 0,
    rowsRejected: 0,
    rejectedSummary: {},
    warnings: {},
    sheetsIgnored: ['Call IVR Details'],
    sheets: [
      { sheet: 'Call Record Report', read: true, rowsRead: 5971, rowsKept: 5971, warnings: {} },
      {
        sheet: 'Call IVR Details',
        read: false,
        rowsRead: 0,
        rowsKept: 0,
        warnings: { 'sheet.missing': 1 },
      },
    ],
    reconciles: true,
    reconciliation: {},
    ...overrides,
  }
}
