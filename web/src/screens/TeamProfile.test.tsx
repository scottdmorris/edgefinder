// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { chosenFromHash, findMatches } from '../lib/search'
import { TeamView } from './TeamProfile'
import type { PlayerOption, TeamOption, TeamProfile } from '../lib/api'

afterEach(cleanup)

const players: PlayerOption[] = [
  { id: 1, name: 'Jayson Tatum', team: 'BOS', plain: 'Jayson Tatum' },
  { id: 2, name: 'Luka Dončić', team: 'LAL', plain: 'Luka Doncic' },
]
const teams: TeamOption[] = [
  { code: 'BOS', name: 'Boston Celtics', logo: '', plain: 'boston celtics' },
  { code: 'LAL', name: 'Los Angeles Lakers', logo: '', plain: 'los angeles lakers' },
]

it('finds teams by name or code ahead of players, and ignores accents', () => {
  expect(findMatches('celt', players, teams).map((m) => m.kind)).toEqual(['team'])
  expect(findMatches('bos', players, teams)[0]).toEqual({ kind: 'team', option: teams[0] })
  const luka = findMatches('doncic', players, teams)
  expect(luka).toEqual([{ kind: 'player', option: players[1] }])
  expect(findMatches('  ', players, teams)).toEqual([])
})

it('reads a team or a player from the address, and nothing from a bad one', () => {
  expect(chosenFromHash('#/players?team=bos')).toEqual({ kind: 'team', code: 'BOS' })
  expect(chosenFromHash('#/players?id=42')).toEqual({ kind: 'player', id: 42 })
  expect(chosenFromHash('#/players?team=../x')).toBeNull()
  expect(chosenFromHash('#/players')).toBeNull()
})

const team: TeamProfile = {
  code: 'BOS', name: 'Boston Celtics', season: '2026-27', logo: '', color: '#007a33',
  record: { wins: 10, losses: 2, home: '5-0', away: '5-2', last10: '9-1', streak: 'W5' },
  teams_in_league: 30,
  ratings: { games: 12, ppg: 114.2, opp_ppg: 104.1, ortg: 102.3, drtg: 93.2, net: 9.0, pace: 111.1,
    ppg_rank: 8, opp_ppg_rank: 3, ortg_rank: 10, drtg_rank: 2, net_rank: 2, pace_rank: 25 },
  results: [{ date: '2026-11-11', opponent: 'TOR', home: false, result: 'W', score: '98-93' }],
  roster: [{ id: 1, name: 'Jayson Tatum', photo: '', games: 12, minutes: 34, pts: 26.3, reb: 8, ast: 5, fg3m: 3 }],
  tonight: [{ id: 1, name: 'Jayson Tatum', line: 26.5, over: -115, under: -111, projection: 23.1, game: 'DAL @ BOS', date: '2026-11-15' }],
  injury_report: true,
  injuries: [{ name: 'Paul George', status: 'OUT', detail: 'knee' }, { name: 'Bench Guy', status: 'DAY-TO-DAY', detail: '' }],
  absences: [{ id: 3, name: 'Paul George', status: 'OUT', detail: 'knee', with_games: 8, without_games: 4,
    teammates: [{ id: 1, name: 'Jayson Tatum', photo: '', games_with: 8, games_without: 4, pts_with: 24, pts_without: 29.5, min_with: 33, min_without: 36 }] }],
}

it('shows the record, ranks, who is out with the teammates split, and links to players', () => {
  const onPlayer = vi.fn()
  render(<TeamView team={team} onPlayer={onPlayer} />)
  expect(screen.getByText(/10-2 · home 5-0 · away 5-2 · last 10 9-1 · W5/)).toBeTruthy()
  expect(screen.getByText('2nd')).toBeTruthy()                    // defense rank
  expect(screen.getByText('+5.5')).toBeTruthy()                   // Tatum without George
  expect(screen.getByText(/Bench Guy \(day-to-day\)/)).toBeTruthy()
  fireEvent.click(screen.getAllByRole('button', { name: /Jayson Tatum/ })[0])
  expect(onPlayer).toHaveBeenCalledWith(1)
})

it('says so when the injury report could not be read', () => {
  render(<TeamView team={{ ...team, injury_report: false, injuries: [], absences: [] }} onPlayer={vi.fn()} />)
  expect(screen.getByText("The injury report couldn't be read right now.")).toBeTruthy()
})
