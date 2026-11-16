// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'

const mocks = vi.hoisted(() => {
  function deferred() {
    let resolve!: () => void
    let reject!: (error: Error) => void
    const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no })
    return { promise, resolve, reject }
  }
  return {
    parlay: deferred(), review: deferred(), picks: deferred(),
    imports: vi.fn(),
    live: vi.fn(() => ({ data: [{ state: 'live' }], error: null, receivedAt: 123 })),
    poll: vi.fn(() => ({ data: { snapshot: { level: 'ok', text: 'Lines last checked just now' } } })),
  }
})

vi.mock('./lib/live', () => ({ useLiveGames: mocks.live }))
vi.mock('./lib/poll', () => ({ usePoll: mocks.poll }))
vi.mock('./screens/Parlay', async () => {
  mocks.imports('parlay')
  await mocks.parlay.promise
  return { Parlay: () => <h1>Parlay screen</h1> }
})
vi.mock('./screens/Review', async () => {
  mocks.imports('review')
  await mocks.review.promise
  return { Review: () => <h1>Review screen</h1> }
})
vi.mock('./screens/Picks', async () => {
  mocks.imports('picks')
  await mocks.picks.promise
  return { Picks: () => <h1>Picks screen</h1> }
})
vi.mock('./screens/Live', () => {
  mocks.imports('live')
  return { Live: () => <h1>Live screen</h1> }
})
vi.mock('./screens/Players', () => {
  mocks.imports('players')
  return { Players: () => <h1>Players screen</h1> }
})
vi.mock('./screens/Record', () => {
  mocks.imports('record')
  return { Record: () => <h1>Record screen</h1> }
})

function navigate(hash: string) {
  act(() => {
    window.history.replaceState(null, '', hash)
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  })
}

beforeEach(() => {
  window.history.replaceState(null, '', '#/parlay')
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
  mocks.live.mockClear()
  mocks.poll.mockClear()
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('loads only the initial screen on demand and keeps header and navigation visible', async () => {
  render(<App />)
  expect(screen.getByRole('status').textContent).toBe('Loading Parlay…')
  expect(screen.getByRole('navigation', { name: 'Sections' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Ball Knowledge' })).toBeTruthy()
  expect(screen.getByRole('link', { name: '1 live' })).toBeTruthy()
  expect(screen.getByText('Lines just now')).toBeTruthy()
  await waitFor(() => expect(mocks.imports).toHaveBeenCalledWith('parlay'))
  expect(mocks.imports.mock.calls.map(([id]) => id)).toEqual(['parlay'])
  await act(async () => { mocks.parlay.resolve() })
  expect(await screen.findByRole('heading', { name: 'Parlay screen' })).toBeTruthy()
  expect(screen.queryByRole('status')).toBeNull()
  expect(mocks.live).toHaveBeenLastCalledWith(60_000)
  expect(mocks.poll).toHaveBeenLastCalledWith(expect.any(Function), 60_000, 'health')
})

it('navigates away from a pending screen and updates title, active link and live polling', async () => {
  navigate('#/review')
  render(<App />)
  expect(screen.getByRole('status').textContent).toBe('Loading Last night…')
  expect(document.title).toBe('Last night · Ball Knowledge')
  expect(screen.getByRole('link', { name: 'Last night' }).getAttribute('aria-current')).toBe('page')
  navigate('#/live')
  expect(await screen.findByRole('heading', { name: 'Live screen' })).toBeTruthy()
  expect(document.title).toBe('Live · Ball Knowledge')
  expect(screen.getByRole('link', { name: 'Live' }).getAttribute('aria-current')).toBe('page')
  expect(mocks.live).toHaveBeenLastCalledWith(10_000)
  await act(async () => { mocks.review.resolve() })
  expect(screen.queryByRole('heading', { name: 'Review screen' })).toBeNull()
  navigate('#/record')
  expect(await screen.findByRole('heading', { name: 'Record screen' })).toBeTruthy()
  expect(mocks.live).toHaveBeenLastCalledWith(60_000)
  expect(window.scrollTo).toHaveBeenCalledWith(0, 0)
})

it('supports hashes with query parameters and falls back to Parlay for unknown hashes', async () => {
  navigate('#/players?team=BOS')
  render(<App />)
  expect(await screen.findByRole('heading', { name: 'Players screen' })).toBeTruthy()
  await act(async () => { mocks.parlay.resolve() })
  navigate('#/unknown')
  expect(await screen.findByRole('heading', { name: 'Parlay screen' })).toBeTruthy()
  expect(document.title).toBe('Parlay · Ball Knowledge')
})

it('contains a failed chunk, offers an explicit reload and allows navigation to recover', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  navigate('#/picks')
  render(<App />)
  expect(screen.getByRole('status').textContent).toBe('Loading Picks…')
  await waitFor(() => expect(mocks.imports).toHaveBeenCalledWith('picks'))
  await act(async () => { mocks.picks.reject(new Error('Failed to fetch dynamically imported module')) })
  expect((await screen.findByRole('alert')).textContent).toContain('This section could not load')
  expect(screen.getByRole('button', { name: 'Reload page' })).toBeTruthy()
  expect(screen.getByRole('navigation', { name: 'Sections' })).toBeTruthy()
  navigate('#/live')
  expect(await screen.findByRole('heading', { name: 'Live screen' })).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
  // A rejected lazy import remains rejected; revisiting shows the recovery UI again.
  navigate('#/picks')
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(mocks.imports.mock.calls.filter(([id]) => id === 'picks')).toHaveLength(1)
})
