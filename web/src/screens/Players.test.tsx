// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type PlayerProfile } from '../lib/api'
import { Players } from './Players'

vi.mock('./TeamProfile', () => ({ TeamProfile: ({ code }: { code: string }) => <h2>Team {code}</h2> }))
const profile: PlayerProfile = { id: 1, name: 'Jayson Tatum', team: 'BOS', photo: '', logo: '', color: '#007A33',
  season: '2026-27', season_games: 2, averages: { pts: 25, reb: 5, ast: 4, fg3m: 2, minutes: 30 }, tonight: null,
  games: [28, 22].map((pts, index) => ({ date: `2026-11-${14 - index}`, pts, reb: 5, ast: 4, fg3m: 2, minutes: 30,
    season: '2026-27', opponent: 'LAL', home: true, result: 'W' })) }
beforeEach(() => {
  window.history.replaceState(null, '', '#/players')
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  vi.spyOn(api, 'players').mockResolvedValue([{ id: 1, name: 'Jayson Tatum', team: 'BOS', plain: 'jaysontatum' }])
  vi.spyOn(api, 'teams').mockResolvedValue([{ code: 'BOS', name: 'Boston Celtics', logo: '', plain: 'bostonceltics' }])
  vi.spyOn(api, 'player').mockResolvedValue(profile)
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })
function navigate(hash: string) {
  act(() => { window.history.replaceState(null, '', hash); window.dispatchEvent(new HashChangeEvent('hashchange')) })
}
it('follows query-only navigation between teams, players and the bare search screen', async () => {
  navigate('#/players?team=BOS')
  render(<Players />)
  expect(screen.getByRole('heading', { name: 'Team BOS' })).toBeTruthy()
  navigate('#/players?team=LAL')
  expect(screen.getByRole('heading', { name: 'Team LAL' })).toBeTruthy()
  expect(screen.queryByRole('heading', { name: 'Team BOS' })).toBeNull()
  navigate('#/players?id=1')
  expect(await screen.findByText('Jayson Tatum')).toBeTruthy()
  navigate('#/players')
  expect(screen.queryByText('Jayson Tatum')).toBeNull()
})
it('exposes the active search option and still searches teams when players fail', async () => {
  vi.mocked(api.players).mockRejectedValueOnce(new Error('Unavailable'))
  render(<Players />)
  expect(await screen.findByRole('alert')).toBeTruthy()
  const box = screen.getByRole('combobox')
  fireEvent.change(box, { target: { value: 'Boston' } })
  const option = await screen.findByRole('option')
  expect(box.getAttribute('aria-activedescendant')).toBe(option.id)
  fireEvent.keyDown(box, { key: 'ArrowDown' })
  expect(box.getAttribute('aria-activedescendant')).toBe(option.id)
  fireEvent.keyDown(box, { key: 'Enter' })
  expect(screen.getByRole('heading', { name: 'Team BOS' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Retry players' }))
  fireEvent.change(box, { target: { value: 'Jayson' } })
  expect(await screen.findByRole('option', { name: /Jayson Tatum/ })).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
})
it('lists every line on the slate beside the player\'s season and last-10 averages', async () => {
  const line = (stat: string, label: string, value: number, season: number, last10: number) => ({
    stat, label, line: value, over: -110, under: -110, season_avg: season, last10_avg: last10,
    projections: [{ model: 'Simple', mean: value + 1 }] })
  vi.mocked(api.player).mockResolvedValue({ ...profile, tonight: { date: '2026-11-15', game: 'BOS @ NYK',
    lines: [line('points', 'Points', 26.5, 25, 27.2), line('rebounds', 'Rebounds', 7.5, 8.1, 6.4)] } })
  navigate('#/players?id=1')
  render(<Players />)
  const table = await screen.findByRole('table', { name: 'Lines on the slate' })
  const rows = table.querySelectorAll('tbody tr')
  expect([...rows].map((row) => row.textContent)).toEqual([
    expect.stringMatching(/Points.*26\.5.*25\.0.*27\.2/), expect.stringMatching(/Rebounds.*7\.5.*8\.1.*6\.4/)])
})
it('makes individual chart values available by focus/tap and names the result column', async () => {
  navigate('#/players?id=1')
  render(<Players />)
  const bar = await screen.findByRole('button', { name: /2026-11-13.*22 points/ })
  fireEvent.focus(bar)
  expect(screen.getByRole('status').textContent).toContain('2026-11-13')
  const other = screen.getByRole('button', { name: /2026-11-14.*28 points/ })
  fireEvent.click(other)
  expect(screen.getByRole('status').textContent).toContain('28 points')
  expect(screen.getByRole('columnheader', { name: 'Result' })).toBeTruthy()
  expect(screen.getByRole('region', { name: 'Recent player games' }).tabIndex).toBe(0)
})
