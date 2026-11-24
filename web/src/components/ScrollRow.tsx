// A row that scrolls sideways, made easy with a mouse: arrow buttons at either end appear
// on wider screens whenever there is more to see that way. Touch screens just swipe.
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

const STEP_SHARE = 0.8         // each arrow click moves most of a screen's width

export function ScrollRow({ label, children }: { label: string; children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null)
  const [more, setMore] = useState({ left: false, right: false })
  const measure = useCallback(() => {
    const el = box.current
    if (!el) return
    setMore({ left: el.scrollLeft > 1, right: el.scrollLeft + el.clientWidth < el.scrollWidth - 1 })
  }, [])
  useEffect(() => {
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [measure, children])
  const go = (direction: number) => {
    const el = box.current
    if (el) el.scrollBy({ left: direction * el.clientWidth * STEP_SHARE, behavior: 'smooth' })
  }
  const arrow = (direction: number, shown: boolean) => shown && (
    <button type="button" aria-label={`Scroll ${label} ${direction < 0 ? 'left' : 'right'}`} onClick={() => go(direction)}
      className={`absolute top-1/2 z-10 hidden size-9 -translate-y-1/2 place-items-center rounded-full border border-line-strong bg-raised-2 text-lg font-black shadow-lg hover:bg-raised sm:grid ${direction < 0 ? '-left-2' : '-right-2'}`}>
      {direction < 0 ? '‹' : '›'}
    </button>
  )
  return <div className="relative">
    {arrow(-1, more.left)}
    <div ref={box} role="group" aria-label={label} onScroll={measure} className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto scroll-smooth px-1 pb-1">
      {children}
    </div>
    {arrow(1, more.right)}
  </div>
}
