/** Minutes as hours and minutes: 480 is "8h", 450 is "7h 30m", 45 is "45m", 0 is "0m". */
export function formatMinutes(minutes: number): string {
  const rounded = Math.round(minutes)
  const hours = Math.floor(rounded / 60)
  const rest = rounded % 60
  if (hours === 0) return `${rest}m`
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`
}
