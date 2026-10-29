export interface Pt {
  x: number
  y: number
}

const f = (n: number) => (Number.isFinite(n) ? n.toFixed(1) : '0.0')

/** Smooth path through the points (Catmull-Rom turned into cubic curves). One point gives a
 *  lone move so nothing is drawn as a line; none gives ''. Never emits NaN. */
export function smoothPath(points: ReadonlyArray<Pt>): string {
  if (points.length === 0) return ''
  const p = points
  let d = `M${f(p[0]!.x)} ${f(p[0]!.y)}`
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[i - 1] ?? p[i]!
    const p1 = p[i]!
    const p2 = p[i + 1]!
    const p3 = p[i + 2] ?? p2
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 }
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 }
    d += ` C${f(c1.x)} ${f(c1.y)} ${f(c2.x)} ${f(c2.y)} ${f(p2.x)} ${f(p2.y)}`
  }
  return d
}

/** Maps values to y inside [top, top+height]; a flat series sits in the middle. */
export function scaleY(values: ReadonlyArray<number>, top: number, height: number) {
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo
  return (v: number) => (span === 0 ? top + height / 2 : top + height - ((v - lo) / span) * height)
}
