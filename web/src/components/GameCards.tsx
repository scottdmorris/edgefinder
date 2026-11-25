// The day's games as cards, like a sportsbook's game list: both teams with their moneyline and
// the market's win chance, tip-off time and how many players have props. Choosing one opens
// that game's props by team.
import type { BoardGame, Moneyline } from '../lib/api'
import { american } from '../lib/ladder'
import { ScrollRow } from './ScrollRow'

export function tipTime(tip: string | null | undefined): string {
  if (!tip) return 'Time TBD'
  const when = new Date(tip)
  return Number.isNaN(when.getTime()) ? 'Time TBD' : when.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export type SidePrice = { odds: string; pct: string }

/** One side's moneyline and no-vig win chance as shown ("+128", "42%"), or null with no line. */
export function sidePrice(line: Moneyline | null | undefined, side: 'away' | 'home'): SidePrice | null {
  if (!line) return null
  const pct = side === 'away' ? line.away_pct : line.home_pct
  return { odds: american(side === 'away' ? line.away_odds : line.home_odds), pct: `${Math.round(pct)}%` }
}

function Side({ code, logo, price }: { code?: string; logo?: string; price: SidePrice | null }) {
  return <span className="flex items-center gap-1.5">
    {logo ? <img src={logo} alt="" className="size-6" loading="lazy" /> : <span className="size-6" />}
    <span className="font-black">{code}</span>
    {price && <span className="ml-auto flex gap-2 pl-3 tabular-nums">
      <span className="font-bold">{price.odds}</span>
      <span className="w-8 text-right text-muted">{price.pct}</span>
    </span>}
  </span>
}

/** `list` lays the games out as a grid to choose from (the Parlay home); `row` is one sideways
 * strip. With `all`, the first card clears the choice. */
export function GameCards({ games, value, all, onChange, layout = 'row', picks = {} }: {
  games: BoardGame[]; value: string; all?: string; onChange: (game: string) => void; layout?: 'row' | 'list'
  /** how many of the model's tracked picks each game holds, by game name */
  picks?: Record<string, number>
}) {
  const card = `min-h-11 shrink-0 rounded-2xl border px-3 py-2 text-left text-sm transition-colors ${layout === 'list' ? 'w-full' : ''}`
  const tone = (on: boolean) => (on ? 'border-text bg-raised-2' : 'border-line bg-raised hover:border-line-strong')
  const cards = <>
    {all !== undefined && <button type="button" aria-pressed={value === all} onClick={() => onChange(all)} className={`${card} ${tone(value === all)} font-bold`}>
      All games
    </button>}
    {games.map((g) => {
      const on = value === g.game
      const players = `${g.players ?? 0} player${g.players === 1 ? '' : 's'}`
      const count = picks[g.game] ?? 0
      const pickText = count ? `${count} model pick${count === 1 ? '' : 's'}` : ''
      const away = g.away ?? g.short.split(' @ ')[0]
      const home = g.home ?? g.short.split(' @ ')[1]
      const [awayPrice, homePrice] = [sidePrice(g.moneyline, 'away'), sidePrice(g.moneyline, 'home')]
      const odds = awayPrice && homePrice
        ? `, ${away} ${awayPrice.odds} ${awayPrice.pct} to win, ${home} ${homePrice.odds} ${homePrice.pct} to win` : ''
      return <button key={g.game} type="button" aria-pressed={on} onClick={() => onChange(g.game)}
        aria-label={`${g.short}, ${g.started ? 'started, ' : ''}${tipTime(g.tip)}${odds}, ${players}${pickText ? `, ${pickText}` : ''}`}
        title={g.moneyline ? 'Moneyline and win chance with the book’s margin removed' : undefined}
        className={`${card} ${tone(on)} ${g.moneyline ? 'min-w-48' : 'min-w-36'} ${g.started ? 'opacity-60' : ''}`}>
        <div className="flex flex-col gap-1">
          <Side code={away} logo={g.away_logo} price={awayPrice} />
          <Side code={home} logo={g.home_logo} price={homePrice} />
        </div>
        <div className="mt-1.5 text-[11px] text-muted">{g.started && <b className="text-warn">Started · </b>}{tipTime(g.tip)} · {players}
          {pickText && <> · <b className="text-good">★ {pickText}</b></>}</div>
      </button>
    })}
  </>
  return layout === 'list'
    ? <div role="group" aria-label="Games" className="grid gap-2 sm:grid-cols-2">{cards}</div>
    : <ScrollRow label="Games">{cards}</ScrollRow>
}
