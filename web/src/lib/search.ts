// The Players screen's search: what the address asks for, and which teams and players match.
import type { PlayerOption, TeamOption } from './api'

export const MATCHES_SHOWN = 8
export const TEAMS_SHOWN = 3

export type Chosen = { kind: 'player'; id: number } | { kind: 'team'; code: string }
export type Match = { kind: 'player'; option: PlayerOption } | { kind: 'team'; option: TeamOption }

/** "Dončić" and "doncic" are the same search. */
export const plain = (text: string): string => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

/** What the address asks for: #/players?id=123 or #/players?team=BOS */
export function chosenFromHash(hash: string): Chosen | null {
  const params = new URLSearchParams(hash.split('?')[1])
  const team = params.get('team')
  if (team && /^[A-Za-z]{2,4}$/.test(team)) return { kind: 'team', code: team.toUpperCase() }
  const id = Number(params.get('id'))
  return Number.isFinite(id) && id > 0 ? { kind: 'player', id } : null
}

/** Teams whose name or code matches, then players; accents and case ignored. */
export function findMatches(query: string, options: PlayerOption[], teams: TeamOption[]): Match[] {
  const q = plain(query.trim())
  if (!q) return []
  const team = teams.filter((t) => t.code.toLowerCase() === q || t.plain.split(' ').some((w) => w.startsWith(q)))
  const starts = options.filter((o) => plain(o.name).split(' ').some((w) => w.startsWith(q)) || plain(o.name).startsWith(q))
  const contains = options.filter((o) => !starts.includes(o) && plain(o.name).includes(q))
  return [
    ...team.slice(0, TEAMS_SHOWN).map((option) => ({ kind: 'team' as const, option })),
    ...[...starts, ...contains].slice(0, MATCHES_SHOWN).map((option) => ({ kind: 'player' as const, option })),
  ]
}
