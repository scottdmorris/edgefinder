// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import type { MissReportRow } from '../lib/api'
import { MissReport } from './MissReport'

afterEach(cleanup)

it('switches to the available stat and model for another book', () => {
  const metric = { n: 20, win_pct: 70, break_even_pct: 75, units: -2, roi_pct: -10, miss: 1.2 }
  const first: MissReportRow = { ...metric, book: 'fanduel', stat: 'points', model: 'context-v2',
    model_name: 'Shot profile', sides: { over: metric }, prices: {}, disagreement: null }
  const second = { ...first, book: 'kalshi', stat: 'rebounds', model: 'ewma-v1',
    model_name: 'Recent average', n: 25, break_even_pct: 80, roi_pct: -12 }
  render(<MissReport rows={[first, second]} />)
  expect(within(screen.getByRole('table', { name: 'Over and under' })).getByText('75.0%')).toBeTruthy()
  fireEvent.change(screen.getByRole('combobox', { name: 'Book' }), { target: { value: 'kalshi' } })
  expect((screen.getByRole('combobox', { name: 'Stat' }) as HTMLSelectElement).value).toBe('rebounds')
  expect((screen.getByRole('combobox', { name: 'Model' }) as HTMLSelectElement).value).toBe('ewma-v1')
  expect(screen.getByText('80.0%')).toBeTruthy()
  expect(screen.getByText('-12.0%')).toBeTruthy()
})
