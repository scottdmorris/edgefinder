// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Idea, Leg } from '../lib/api'
import { QuickAdds, type QuickAdd } from './QuickAdds'
import { SuggestedSlip } from './SuggestedSlip'

afterEach(cleanup)
const leg = (id: number, player: string) => ({ id, player, photo: '', bet: '20+ points', odds: -120, game_short: 'TOR @ PHI',
  average: { season: 24.1, last10: 25 } }) as Leg
const legs = new Map([[1, leg(1, 'First Player')], [2, leg(2, 'Second Player')], [3, leg(3, 'Third Player')]])
const ideas: Idea[] = [{ legs: [1, 2], chance_pct: 33.4, pays: 3.35, ev_pct: 2 }, { legs: [3], chance_pct: 61, pays: 1.6, ev_pct: 1 }]
const base = { legs, sameGame: false, styles: ['Safer', 'Balanced', 'Bigger payouts'], style: 'Balanced', onStyle: vi.fn(), inUse: [] as number[], onUse: vi.fn() }

it('leads with one slip, its chance and what ten dollars returns, and puts it on the slip', () => {
  const onUse = vi.fn()
  render(<SuggestedSlip {...base} ideas={ideas} onUse={onUse} />)
  expect(screen.getByText('First Player')).toBeTruthy()
  expect(screen.getByText('33%')).toBeTruthy()
  expect(screen.getByText('$33.50')).toBeTruthy()
  expect(screen.queryByText('Third Player')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Use this slip' }))
  expect(onUse).toHaveBeenCalledWith([1, 2])
})

it('steps to another suggestion and wraps around', () => {
  render(<SuggestedSlip {...base} ideas={ideas} />)
  fireEvent.click(screen.getByRole('button', { name: 'Another' }))
  expect(screen.getByText('Third Player')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Another' }))
  expect(screen.getByText('First Player')).toBeTruthy()
})

it('says when the suggestion is already the slip, and switches style', () => {
  const onStyle = vi.fn()
  render(<SuggestedSlip {...base} ideas={ideas} inUse={[2, 1]} onStyle={onStyle} />)
  expect(screen.getByRole('button', { name: '✓ On your slip' }).getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(screen.getByRole('radio', { name: 'Safer' }))
  expect(onStyle).toHaveBeenCalledWith('Safer')
})

it('explains an empty result instead of showing a blank card', () => {
  render(<SuggestedSlip {...base} ideas={[]} />)
  expect(screen.getByText(/Nothing fits this style here/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Use this slip' })).toBeNull()
})

const quick = (kind: QuickAdd['kind'], player: string, legId: number | null): QuickAdd => ({
  key: `${kind}-${player}`, kind, player, photo: '', bet: 'Under 9.5 points', odds: -118, game: 'BKN @ NOP',
  why: 'Projects 6.5', figure: '+11.3%', legId })

it('lists quick adds of every kind, filters by kind, and adds one to the slip', () => {
  const toggle = vi.fn()
  render(<QuickAdds items={[quick('Model pick', 'Pick Guy', 7), quick('Steady', 'Steady Guy', 8)]} selected={[8]} toggle={toggle} />)
  expect(screen.getByRole('button', { name: 'Remove Steady Guy Under 9.5 points' }).getAttribute('aria-pressed')).toBe('true')
  fireEvent.click(screen.getByRole('button', { name: 'Add Pick Guy Under 9.5 points' }))
  expect(toggle).toHaveBeenCalledWith(7)
  fireEvent.click(screen.getByRole('radio', { name: 'Steady' }))
  expect(screen.queryByText('Pick Guy')).toBeNull()
})

it('says why a pick cannot be added when this price source lacks its number', () => {
  render(<QuickAdds items={[{ ...quick('Model pick', 'Pick Guy', null), missing: "FanDuel line. Kalshi doesn't offer this number." }]} selected={[]} toggle={vi.fn()} />)
  expect(screen.getByText('Pick Guy')).toBeTruthy()
  expect(screen.getByText("FanDuel line. Kalshi doesn't offer this number.")).toBeTruthy()
  expect(screen.queryByRole('button')).toBeNull()
})
