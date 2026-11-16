// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { BookBadge } from './BookBadge'

afterEach(cleanup)
it('retains the accessible book name and falls back to text if the image fails', () => {
  const { container } = render(<button><BookBadge book="fanduel" /></button>)
  expect(screen.getByRole('button', { name: 'FanDuel' })).toBeTruthy()
  fireEvent.error(container.querySelector('img')!)
  expect(screen.getByText('FanDuel').className).not.toContain('sr-only')
  expect(container.querySelector('img')).toBeNull()
})
it('keeps an unknown price source readable', () => {
  render(<BookBadge book="Another book" />)
  expect(screen.getByText('Another book')).toBeTruthy()
})
