import { useEffect, useState } from 'react'
import { api } from './lib/api'
import { usePoll } from './lib/poll'
import { Live } from './screens/Live'
import { Parlay } from './screens/Parlay'
import { Picks } from './screens/Picks'
import { Players } from './screens/Players'
import { Record } from './screens/Record'
import { Review } from './screens/Review'

// Screens are switched by the address (#/parlay, #/live…) so the back button and links work.
const SCREENS = [
  { id: 'parlay', label: 'Parlay' },
  { id: 'live', label: 'Live' },
  { id: 'review', label: 'Last night' },
  { id: 'players', label: 'Players' },
  { id: 'picks', label: 'Picks' },
  { id: 'record', label: 'Record' },
] as const
type ScreenId = (typeof SCREENS)[number]['id']
const LIVE_CHECK_MS = 60_000

function current(): ScreenId {
  const id = window.location.hash.replace('#/', '').split('?')[0]
  return (SCREENS.find((s) => s.id === id)?.id ?? 'parlay') as ScreenId
}

export default function App() {
  const [screen, setScreen] = useState<ScreenId>(current)
  const health = usePoll(api.health, LIVE_CHECK_MS, 'health').data
  const games = usePoll(api.live, LIVE_CHECK_MS, 'header')
  const live = games.data?.filter((g) => g.state === 'live').length ?? 0

  useEffect(() => {
    const onHash = () => { setScreen(current()); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    document.title = `${SCREENS.find((s) => s.id === screen)?.label} · Ball Knowledge`
  }, [screen])

  return (
    <div className="mx-auto max-w-6xl px-4 pb-28 pt-4 sm:px-6">
      <header className="flex items-center justify-between gap-3">
        <a href="#/parlay" className="flex items-center gap-2.5">
          <img src="/logo-mark.svg" alt="" className="size-8" />
          <span className="text-xl font-black tracking-tight">Ball Knowledge</span>
        </a>
        <div className="flex items-center gap-2">
          {live > 0 && (
            <a href="#/live" className="flex items-center gap-1.5 rounded-full border border-bad/40 px-3 py-1.5 text-xs font-bold text-bad">
              <span className="live-dot size-1.5 rounded-full bg-bad" />{live} live
            </a>
          )}
          {health && (
            <span className={`hidden rounded-full border px-3 py-1.5 text-xs font-bold sm:inline-block ${
              health.snapshot.level === 'ok' ? 'border-line text-muted' : 'border-warn/50 text-warn'}`}>
              {health.snapshot.text.replace('Lines last checked ', 'Lines ')}
            </span>
          )}
        </div>
      </header>

      {health && health.snapshot.level !== 'ok' && (
        <div className="mt-3 rounded-2xl border border-warn/40 bg-warn/5 px-4 py-2.5 text-sm text-warn sm:hidden">{health.snapshot.text}</div>
      )}

      <nav className="no-scrollbar -mx-4 mt-4 mb-6 overflow-x-auto px-4 sm:mx-0 sm:px-0" aria-label="Sections">
        <div className="inline-flex gap-1 rounded-full border border-line bg-raised p-1">
          {SCREENS.map((s) => (
            <a key={s.id} href={`#/${s.id}`} aria-current={screen === s.id ? 'page' : undefined}
              className={`whitespace-nowrap rounded-full px-3.5 py-2 text-sm font-bold transition-colors sm:px-4 ${
                screen === s.id ? 'bg-button text-button-text' : 'text-muted hover:text-text'}`}>
              {s.label}
            </a>
          ))}
        </div>
      </nav>

      <main>
        {screen === 'parlay' && <Parlay />}
        {screen === 'live' && <Live />}
        {screen === 'review' && <Review />}
        {screen === 'players' && <Players />}
        {screen === 'picks' && <Picks />}
        {screen === 'record' && <Record />}
      </main>

      <footer className="mt-16 border-t border-line pt-5 text-xs leading-relaxed text-muted">
        <p>
          Paper tracking only: no money is staked, and no model wins every night. Nothing here is betting advice. Never
          stake money you can't afford to lose. Problem gambling help: 1-800-GAMBLER.
        </p>
        <p className="mt-2">
          Player and game data from NBA.com, prices from FanDuel (via The Odds API) and Kalshi. ·{' '}
          <a href="/api/docs" className="underline hover:text-text">API</a>
        </p>
      </footer>
    </div>
  )
}
