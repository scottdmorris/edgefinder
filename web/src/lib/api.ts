// Typed access to the Ball Knowledge API (src/edgefinder/api). Every number here comes from the
// Python side; the front end only shows it.

export type Leg = {
  id: number
  player: string
  player_id: number
  photo: string
  game: string
  game_short: string
  stat: string
  stat_label: string
  side: string // "Over", "Under" or "25+"
  line: number
  bet: string
  odds: number
  model_pct: number | null
  market_pct: number | null
  chance_pct: number | null
  ev_pct: number | null
  average: { season: number | null; last10: number | null } | null
}

export type Gap = {
  leg_id: number | null
  player: string
  player_id: number
  photo: string
  game_short: string
  bet: string
  odds: number
  edge_pct: number
  price_pct: number
  reference: string
  reference_pct: number
  estimated: boolean
}

export type Board = {
  date: string
  day_label: string
  days: { date: string; label: string }[]
  book: string
  books: { id: string; name: string }[]
  model: string
  models: { id: string; short: string; name: string }[]
  summary: { games: number; props: number; gaps: number }
  games: { game: string; short: string }[]
  legs: Leg[]
  gaps: Gap[]
  styles: string[]
  default_style: string
}

export type Idea = { legs: number[]; chance_pct: number; pays: number; ev_pct: number }

export type SlipPrice = {
  legs: number
  chance_pct?: number
  one_in?: string
  independent_pct?: number
  decimal?: number
  fair_american?: number
  ev_pct?: number
  verdict?: string
  stake?: number
  to_win?: number
  total_return?: number
  expected?: number
}

export type Health = {
  snapshot: { level: string; text: string }
  settle: { level: string; text: string }
}

export type Market = { date?: string; book?: string; model?: string }

// ---- live -----------------------------------------------------------------------------------------

export type Side = {
  team: string
  logo: string
  color: string
  score: number
  timeouts: number
  bonus: boolean
  fouls: number | null
}

export type GameCard = {
  id: string
  state: 'upcoming' | 'live' | 'final'
  status: string
  away: Side
  home: Side
}

export type Shot = {
  n: number
  team: string
  x: number
  y: number
  made: boolean
  three: boolean
  period: number
  period_label: string
  text: string
}

export type BoxRow = {
  id: number
  photo: string
  on_court: boolean
  Player: string
  Min: number
  Pts: number
  Reb: number
  Ast: number
  FG: string
  '3PT': string
  FT: string
  Stl: number
  Blk: number
  TO: number
  PF: number
  '+/-': string
}

export type Play = { order: number; period: string; clock: string; team: string; text: string; score: string }

export type GameDetail = GameCard & {
  detail: null | {
    quarters: { columns: string[]; rows: { team: string; values: number[] }[] }
    shots: Shot[]
    compare: { label: string; away_text: string; home_text: string; away_share: number; ahead: string }[]
    leaders: { id: number; name: string; photo: string; team: string; stat: string; value: number }[]
    plays: Play[]
    box: Record<string, { starters: BoxRow[]; bench: BoxRow[] }>
    foul_trouble: { name: string; fouls: number; team: string }[]
  }
}

export type TrackedLeg = {
  id: number
  player: string
  bet: string
  photo: string
  status: string
  have: number | null
  target: number
  progress: number
  detail: string
  game: string
}

export type Tracked = { status: string; legs: TrackedLeg[] }

// ---- record ---------------------------------------------------------------------------------------

export type ModelRecord = {
  id: string
  name: string
  short: string
  record: string
  picks: number
  settled: number
  units: number
  roi_pct: number
  verdict: string
  calibration: { bucket: string; lines: number; model: number; market: number; actual: number }[]
}

type GapPart = { logged: number; record: string; units: number }

export type RecordData = {
  empty: boolean
  integrity: { picks: number; graded: number; after_tip: number; first_lock: string | null; last_lock: string | null }
  chain: {
    started: boolean
    intact?: boolean
    entries?: number
    imported?: number
    first_at?: string
    head?: string
    rows?: number
    matched?: number
    clean?: boolean
    published?: { date: string; entry: number; ok: boolean }[]
    problems?: string[]
  }
  clv: { book: string; name: string; measured: number; avg_pct: number; beat_pct: number }[]
  gaps: null | { all: GapPart; exact: GapPart; estimated: GapPart }
  by_book: { book: string; name: string; stats: { stat: string; record: string; settled: number; units: number; roi_pct: number }[] }[]
  models: ModelRecord[]
  alt: { picks: number; settled: number; record: string }
  running: { day: string; model: string; units: number }[]
  days: { day: string; model: string; picks: number; graded: number; record: string; units: number }[]
  log: { day: string; player: string; bet: string; odds: number | null; model: string; locked: string | null; lead: string; result: string | null; units: number | null }[]
}

// ---- players and picks ----------------------------------------------------------------------------

export type PlayerOption = { id: number; name: string; team: string; plain: string }

export type PlayerGame = {
  date: string
  opponent: string
  home: boolean
  result: string
  season: string
  minutes: number
  pts: number
  reb: number
  ast: number
  fg3m: number
}

export type PlayerProfile = {
  id: number
  name: string
  team: string
  photo: string
  logo: string
  color: string
  season: string
  season_games: number
  averages: { pts: number; reb: number; ast: number; fg3m: number; minutes: number }
  tonight: null | {
    date: string
    game: string
    line: number
    over: number
    under: number
    projections: { model: string; mean: number }[]
  }
  games: PlayerGame[]
}

export type Picks = {
  date: string
  days: { date: string; label: string }[]
  models: { id: string; short: string; name: string }[]
  liked: { player: string; player_id: number; photo: string; bet: string; game_short: string; odds: number; projects: number; ev_pct: number; agree: number }[]
  lines: {
    player: string
    player_id: number | null
    photo: string | null
    game_short: string
    line: number
    gap: number
    market_pct: number
    over: number
    under: number
    models: { id: string; proj: number | null; pct: number | null; pick: string }[]
  }[]
}

async function send<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? response.statusText)
  return response.json() as Promise<T>
}

async function get<T>(path: string, params: Record<string, string | undefined> = {}): Promise<T> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value) query.set(key, value)
  const response = await fetch(`${path}${query.size ? `?${query}` : ''}`)
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? response.statusText)
  return response.json() as Promise<T>
}

export const api = {
  health: () => get<Health>('/api/health'),
  board: (market: Market) => get<Board>('/api/board', market),
  ideas: (market: Market, style: string, game?: string) =>
    get<Idea[]>('/api/ideas', { ...market, style, game }),
  slip: (market: Market, legs: number[], stake: number) =>
    send<SlipPrice>('/api/slip', { ...market, legs, stake }),
  live: () => get<GameCard[]>('/api/live'),
  game: (id: string) => get<GameDetail>(`/api/live/${encodeURIComponent(id)}`),
  track: (market: Market, legs: number[]) => send<Tracked>('/api/live/track', { ...market, legs }),
  record: () => get<RecordData>('/api/record'),
  players: () => get<PlayerOption[]>('/api/players'),
  player: (id: number) => get<PlayerProfile>(`/api/players/${id}`),
  picks: (date?: string) => get<Picks>('/api/picks', { date }),
}
