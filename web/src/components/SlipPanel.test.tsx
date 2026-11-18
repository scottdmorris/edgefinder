// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { SlipPanel } from './SlipPanel'
import { api, type Leg, type SlipPrice } from '../lib/api'

vi.mock('../lib/api', () => ({ api: { slip: vi.fn() } }))
const market = { date: '2026-11-12', book: 'kalshi', model: 'ewma-v1' }
const legsById = new Map([[123, { id: 123, player: 'Example', bet: '25+ points', game_short: 'A @ B', odds: -110, photo: '/player.png' } as Leg]])
const props = { market, legs: [123], legsById, onRemove: vi.fn(), onClear: vi.fn() }
let desktop: MediaQueryList
beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(api.slip).mockReset()
  desktop = Object.assign(new EventTarget(), { matches: false }) as unknown as MediaQueryList
  vi.stubGlobal('matchMedia', vi.fn(() => desktop))
  // jsdom has no native dialog implementation. Assert showModal is used; browser
  // focus trapping and background inertness are supplied by that native API.
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) { this.open = true }) })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) { this.open = false }) })
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

it('hides a previous payout immediately when the selected quote changes', async () => {
  vi.mocked(api.slip).mockResolvedValueOnce({ legs: 1, to_win: 50, total_return: 60, chance_pct: 55, expected: 2 })
  const view = render(<SlipPanel {...props} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  expect(screen.queryAllByText(/Estimated profit \$50/).length).toBeGreaterThan(0)
  let resolve!: (p: SlipPrice) => void
  vi.mocked(api.slip).mockReturnValueOnce(new Promise(r => { resolve = r }))
  view.rerender(<SlipPanel {...props} market={{ ...market, model: 'minutes-v1' }} />)
  expect(screen.queryAllByText(/\$50/)).toHaveLength(0)
  expect(screen.queryAllByText(/Recalculating/).length).toBeGreaterThan(0)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  await act(async () => { resolve({ legs: 1, to_win: 20 }) })
  expect(screen.queryAllByText(/Estimated profit \$20/).length).toBeGreaterThan(0)
})

it('never shows an old mobile payout after a pricing failure', async () => {
  vi.mocked(api.slip).mockResolvedValueOnce({ legs: 1, to_win: 50 })
  const view = render(<SlipPanel {...props} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  vi.mocked(api.slip).mockRejectedValueOnce(new Error('Quote expired'))
  view.rerender(<SlipPanel {...props} market={{ ...market, model: 'minutes-v1' }} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  expect(screen.queryAllByText(/\$50/)).toHaveLength(0)
  expect(screen.getByText('Quote expired')).toBeTruthy()
  expect(screen.getByText('Open slip')).toBeTruthy()
})

it.each(['odds', 'model_pct', 'market_pct', 'chance_pct'] as const)(
  'reprices unchanged IDs immediately when selected leg %s changes', async (field) => {
    vi.mocked(api.slip).mockResolvedValueOnce({ legs: 1, to_win: 50 })
    const view = render(<SlipPanel {...props} />)
    await act(async () => { await vi.advanceTimersByTimeAsync(151) })
    let resolve!: (p: SlipPrice) => void
    vi.mocked(api.slip).mockReturnValueOnce(new Promise(r => { resolve = r }))
    const refreshed = new Map([[123, { ...legsById.get(123)!, [field]: field === 'odds' ? 120 : 60 }]])
    view.rerender(<SlipPanel {...props} legsById={refreshed} />)
    expect(screen.queryAllByText(/\$50/)).toHaveLength(0)
    expect(screen.getByText('Recalculating estimate…')).toBeTruthy()
    expect(screen.getByText('Open slip')).toBeTruthy()
    await act(async () => { await vi.advanceTimersByTimeAsync(151) })
    expect(api.slip).toHaveBeenCalledTimes(2)
    await act(async () => { resolve({ legs: 1, to_win: 20 }) })
    expect(screen.getByText('Estimated profit $20.00')).toBeTruthy()
  },
)

it('reprices a board revision even with identical prices and ignores superseded responses', async () => {
  let resolveOld!: (p: SlipPrice) => void
  let resolveNew!: (p: SlipPrice) => void
  const onPriced = vi.fn()
  vi.mocked(api.slip).mockReturnValueOnce(new Promise(r => { resolveOld = r }))
  const view = render(<SlipPanel {...props} onPriced={onPriced} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  vi.mocked(api.slip).mockReturnValueOnce(new Promise(r => { resolveNew = r }))
  view.rerender(<SlipPanel {...props} revision={1} onPriced={onPriced} />)
  await act(async () => { await vi.advanceTimersByTimeAsync(151) })
  await act(async () => { resolveNew({ legs: 1, to_win: 20 }) })
  await act(async () => { resolveOld({ legs: 1, to_win: 99 }) })
  expect(screen.queryAllByText(/\$99/)).toHaveLength(0)
  expect(screen.getByText('Estimated profit $20.00')).toBeTruthy()
  expect(onPriced).toHaveBeenCalledTimes(1)
  // A subsequent reload must hide even a successfully priced, unchanged board.
  view.rerender(<SlipPanel {...props} revision={2} onPriced={onPriced} />)
  expect(screen.queryAllByText(/\$20/)).toHaveLength(0)
})

function openSlip() {
  const opener = screen.getByRole('button', { name: /1 bet/ })
  opener.focus()
  fireEvent.click(opener)
  return { opener, dialog: screen.getByRole('dialog', { name: 'Your slip' }) }
}

it('opens a named native modal, enters focus, and restores the mounted opener on Escape', () => {
  const previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'auto'
  render(<SlipPanel {...props} />)
  const { opener, dialog } = openSlip()
  expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalledTimes(1)
  expect(dialog.getAttribute('open')).not.toBeNull()
  expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: 'Keep browsing' }))
  expect(document.body.style.overflow).toBe('hidden')
  expect(opener.isConnected).toBe(true)
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(opener)
  expect(document.body.style.overflow).toBe('auto')
  document.body.style.overflow = previousOverflow
})

it('associates each Stake label with its own input across surfaces and panel instances', () => {
  const view = render(<SlipPanel {...props} />)
  const { dialog } = openSlip()
  const mobileInput = within(dialog).getByLabelText('Stake') as HTMLInputElement
  const mobileLabel = within(dialog).getByText('Stake') as HTMLLabelElement
  expect(mobileLabel.control).toBe(mobileInput)
  expect(mobileInput.closest('dialog')).toBe(dialog)
  fireEvent.change(mobileInput, { target: { value: '25' } })
  expect(screen.getAllByLabelText('Stake').every(field => (field as HTMLInputElement).value === '25')).toBe(true)
  view.rerender(<><SlipPanel {...props} /><SlipPanel {...props} /></>)
  const fields = screen.getAllByLabelText('Stake')
  expect(new Set(fields.map(field => field.id)).size).toBe(fields.length)
})

it('dismisses on Keep browsing and at the desktop breakpoint, restoring scroll on unmount', () => {
  const view = render(<SlipPanel {...props} />)
  const { opener, dialog } = openSlip()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Keep browsing' }))
  expect(document.activeElement).toBe(opener)
  fireEvent.click(opener)
  act(() => {
    Object.assign(desktop, { matches: true })
    desktop.dispatchEvent(new Event('change'))
  })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.body.style.overflow).toBe('')
  Object.assign(desktop, { matches: false })
  fireEvent.click(opener)
  view.unmount()
  expect(document.body.style.overflow).toBe('')
})

it('wraps the complete player and bet details instead of truncating essential text', () => {
  const player = 'A very long player name with multiple family names'
  const bet = 'Over 25.5 combined points, rebounds and assists'
  render(<SlipPanel {...props} legsById={new Map([[123, { ...legsById.get(123)!, player, bet }]])} />)
  expect(screen.getByText(player).className).toContain('break-words')
  expect(screen.getByText(`${bet} · A @ B`).className).toContain('break-words')
})
