// Price-source identities, not partners or endorsements. Local assets avoid third-party requests.
import { useState } from 'react'

const BOOKS: Record<string, { name: string; asset: string; wordmark?: boolean; light?: boolean }> = {
  fanduel: { name: 'FanDuel', asset: 'fanduel.svg', wordmark: true },
  draftkings: { name: 'DraftKings', asset: 'draftkings.svg' },
  kalshi: { name: 'Kalshi', asset: 'kalshi.png', wordmark: true, light: true },
}

export function BookBadge({ book }: { book: string }) {
  const [failed, setFailed] = useState(false)
  const brand = BOOKS[book.toLowerCase()]
  if (!brand || failed) return <span>{brand?.name ?? book}</span>
  return <span className="inline-flex items-center gap-1.5 align-middle">
    <span className={`inline-flex h-6 items-center justify-center rounded-md px-1.5 ${brand.light ? 'bg-white' : 'bg-[#0A1525]'}`}>
      <img src={`/books/${brand.asset}`} alt="" aria-hidden="true" onError={() => setFailed(true)}
        className={brand.wordmark ? 'h-3.5 w-16 object-contain' : 'size-5 object-contain'} />
    </span>
    <span className={brand.wordmark ? 'sr-only' : ''}>{brand.name}</span>
  </span>
}
