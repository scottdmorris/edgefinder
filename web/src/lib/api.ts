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
  projection?: number | null
  projection_model?: string
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

// A leg the player has reached in nearly all of his recent games, with what it costs.
export type Steady = {
  leg_id: number
  player: string
  player_id: number
  photo: string
  game: string
  game_short: string
  stat: string
  bet: string
  threshold: number
  odds: number
  hits: number
  games: number
  hit_pct: number
  price_pct: number
}

export type Board = {
  date: string
  day_label: string
  days: { date: string; label: string }[]
  book: string
  books: { id: string; name: string }[]
  model: string
  /** the recommended model first; `record` is its graded points record on this price source */
  models: { id: string; short: string; name: string; record?: string | null; settled?: number; recommended?: boolean }[]
  summary: { games: number; props: number; gaps: number }
  games: { game: string; short: string }[]
  legs: Leg[]
  gaps: Gap[]
  steady: Steady[]
  styles: string[]
  default_style: string
}

export type Idea = { legs: number[]; chance_pct: number; pays: number; ev_pct: number }

export type SlipMatches = { matches: { player: string; text: string; candidate_ids: number[]; status: string }[]; note: string }
export type SlipReviewResult = {
  chance_pct: number; ev_pct: number; notes: string[]
  legs: { id: number; player: string; bet: string; projection: number | null; chance_pct: number; ev_pct: number; assessment: string; reason: string; without_chance_pct: number | null }[]
  additions: { id: number; player: string; bet: string; ev_pct: number; with_chance_pct: number }[]
}


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
  received_at?: string
  detail_received_at?: string | null
  detail_available?: boolean
  /** "ORL on a 9-2 run" while one team is heavily outscoring the other; empty otherwise */
  run?: string
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
  game_id?: string | null
  game_state?: 'upcoming' | 'live' | 'final' | null
  player: string
  bet: string
  photo: string
  status: string
  have: number | null
  target: number
  progress: number
  detail: string
  game: string
  /** why the player may be done for the night: fouled out, ejected, or a long stretch off the floor */
  alert?: string
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

// ---- last night ------------------------------------------------------------------------------------

export type ReviewPick = {
  player: string
  player_id: number
  photo: string
  bet: string
  game_short: string
  odds: number | null
  models: string[]
  projects: number | null
  actual: number | null
  status: 'Hit' | 'Missed' | "Didn't play" | 'Not graded yet'
  off_by: number | null
  note: string
}

export type Review = {
  date: string
  label: string
  days: { date: string; label: string }[]
  models: { id: string; short: string; record: string; picks: number; settled: number; units: number | null }[]
  picks: ReviewPick[]
  misses: ReviewPick[]
  pending: number
  kalshi: { record: string; settled: number; units: number | null } | null
}

export type SlipLegQuery = { player_id: number; stat: string; side: string; line: number }
export type GradedSlip = {
  date: string
  status: string
  hit: number
  missed: number
  legs: (SlipLegQuery & { actual: number | null; status: string; note: string })[]
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
  readSlip: async (files: File[]) => {
    const form = new FormData()
    files.forEach((file) => form.append('images', file))
    const response = await fetch('/api/slip/read', { method: 'POST', body: form })
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? 'Could not read images')
    return response.json() as Promise<{ images: { text: string; low_confidence: boolean; lines: number }[] }>
  },
  matchSlip: (market: Market, text: string) => send<SlipMatches>('/api/slip/match', { ...market, text }),
  reviewSlip: (market: Market, legs: number[], confirmed: boolean) => send<SlipReviewResult>('/api/slip/review', { ...market, legs, confirmed }),
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
  review: (date?: string) => get<Review>('/api/review', { date }),
  gradeSlip: (date: string, legs: SlipLegQuery[]) => send<GradedSlip>('/api/review/slip', { date, legs }),
  players: () => get<PlayerOption[]>('/api/players'),
  player: (id: number) => get<PlayerProfile>(`/api/players/${id}`),
  picks: (date?: string) => get<Picks>('/api/picks', { date }),
}
