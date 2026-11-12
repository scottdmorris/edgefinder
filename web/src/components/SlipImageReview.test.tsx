// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, type Leg } from '../lib/api'
import { SlipImageReview } from './SlipImageReview'

vi.mock('../lib/api', () => ({ api: { readSlip: vi.fn(), matchSlip: vi.fn(), reviewSlip: vi.fn() } }))
afterEach(cleanup)
const market = { date: '2026-11-11', book: 'fanduel', model: 'minutes-v1' }
const legs = new Map([[1, { id: 1, player: 'Jalen Brunson', bet: 'Over 26.5 points', odds: -110 } as Leg]])
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.readSlip).mockResolvedValue({ images: [{ text: 'Jalen Brunson\nOver 26.5 Points', low_confidence: false, lines: 2 }] })
  vi.mocked(api.matchSlip).mockResolvedValue({ matches: [{ player: 'Jalen Brunson', text: 'Over 26.5 Points', candidate_ids: [1], status: 'Confirm match' }], note: 'Verify the line.' })
  vi.mocked(api.reviewSlip).mockResolvedValue({ chance_pct: 48, ev_pct: -8, additions: [], notes: [], legs: [
    { id: 1, player: 'Jalen Brunson', bet: 'Over 26.5 points', projection: 25, chance_pct: 48, ev_pct: -8, assessment: 'Consider removing', reason: 'Negative estimated return.', without_chance_pct: null },
  ] })
})

it('reads multiple files, requires confirmation, and only applies an explicitly reviewed slip', async () => {
  const apply = vi.fn()
  render(<SlipImageReview market={market} legs={legs} onApply={apply} />)
  fireEvent.click(screen.getByText('Review a slip from photos'))
  const files = [new File(['a'], 'one.png', { type: 'image/png' }), new File(['b'], 'two.png', { type: 'image/png' })]
  fireEvent.change(screen.getByLabelText('Slip images'), { target: { files } })
  fireEvent.click(screen.getByRole('button', { name: 'Read images' }))
  await waitFor(() => expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toContain('Jalen Brunson'))
  expect(api.readSlip).toHaveBeenCalledWith(files)
  fireEvent.click(screen.getByRole('button', { name: 'Find matching legs' }))
  await screen.findByText('Verify the line.')
  const button = screen.getByRole('button', { name: 'Review confirmed slip' }) as HTMLButtonElement
  expect(button.disabled).toBe(true)
  expect(api.reviewSlip).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(button)
  await screen.findByText(/Consider removing/)
  expect(apply).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Use reviewed slip' }))
  expect(apply).toHaveBeenCalledWith([1])
  fireEvent.click(screen.getByRole('button', { name: 'Remove from reviewed slip' }))
  expect(screen.queryByRole('button', { name: 'Use reviewed slip' })).toBeNull()
})

it('discards confirmed selections when edited text or model changes', async () => {
  const view = render(<SlipImageReview market={market} legs={legs} onApply={vi.fn()} />)
  fireEvent.click(screen.getByText('Review a slip from photos'))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Jalen Brunson Over 26.5 Points' } })
  fireEvent.click(screen.getByRole('button', { name: 'Find matching legs' }))
  await screen.findByText('Verify the line.')
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'different slip' } })
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false)
  view.rerender(<SlipImageReview market={{ ...market, model: 'context-v1' }} legs={legs} onApply={vi.fn()} />)
  expect(screen.queryByText('Verify the line.')).toBeNull()
  expect(api.reviewSlip).not.toHaveBeenCalled()
})
