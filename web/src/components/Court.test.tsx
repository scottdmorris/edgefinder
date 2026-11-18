// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { Court } from './Court'
import type { Shot } from '../lib/api'
afterEach(cleanup)
it('exposes shot details through a touch/keyboard selector and chart markers', () => {
  const shots = [
    { n: 1, team: 'BOS', x: 30, y: 50, made: true, text: 'Tatum makes a layup', period_label: 'Q1' },
    { n: 2, team: 'BOS', x: 20, y: 40, made: false, text: 'Tatum misses a jumper', period_label: 'Q2' },
  ] as Shot[]
  render(<Court shots={shots} colors={{ BOS: '#007A33' }} homeColor="#007A33" homeLogo="" freshFrom={null} />)
  fireEvent.change(screen.getByRole('combobox', { name: 'Shot details' }), { target: { value: '2' } })
  expect(screen.getByRole('status').textContent).toContain('Tatum misses a jumper')
  const first = screen.getByRole('button', { name: /Tatum makes a layup/ })
  fireEvent.click(first)
  expect(screen.getByRole('status').textContent).toContain('Tatum makes a layup')
  fireEvent.keyDown(first, { key: 'ArrowRight' })
  expect(screen.getByRole('status').textContent).toContain('Tatum misses a jumper')
})
