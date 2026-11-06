// Small text helpers shared by screens.

/** "4th Qtr 3:12" -> "Q4 3:12", "2nd Qtr" -> "Q2"; anything else as it is. */
export function shortStatus(status: string): string {
  return status.replace(/\b([1-4])(st|nd|rd|th) Qtr\b/, 'Q$1')
}
