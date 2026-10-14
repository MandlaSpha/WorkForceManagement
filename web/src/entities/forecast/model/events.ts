/** "+20%" or "\u221250%": the change an event makes to calls, with a real minus sign. */
export function changeLabel(pct: number): string {
  return pct < 0 ? `\u2212${Math.abs(pct)}%` : `+${pct}%`
}
