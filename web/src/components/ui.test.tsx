// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { Pills } from './ui'

afterEach(cleanup)
it('uses one radio tab stop and selects/focuses with arrow and boundary keys', () => {
  const changed = vi.fn()
  function Example() {
    const [value, setValue] = useState('a')
    return <Pills label="Stats" value={value} onChange={(v) => { setValue(v); changed(v) }}
      options={[{ id: 'a', label: 'Points' }, { id: 'b', label: 'Assists' }, { id: 'c', label: 'Rebounds' }]} />
  }
  render(<Example />)
  const radios = screen.getAllByRole('radio')
  expect(radios.map((r) => r.tabIndex)).toEqual([0, -1, -1])
  fireEvent.keyDown(radios[0], { key: 'ArrowLeft' })
  expect(changed).toHaveBeenLastCalledWith('c')
  expect(document.activeElement).toBe(radios[2])
  expect(radios[2].getAttribute('aria-checked')).toBe('true')
  fireEvent.keyDown(radios[2], { key: 'Home' })
  expect(document.activeElement).toBe(radios[0])
  fireEvent.keyDown(radios[0], { key: 'End' })
  expect(document.activeElement).toBe(radios[2])
})
