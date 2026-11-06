// Small building blocks shared by every screen.
import type { ReactNode } from 'react'

export function Pills<T extends string>({ options, value, onChange, label }: {
  options: { id: T; label: string }[]
  value: T
  onChange: (id: T) => void
  label?: string
}) {
  return (
    <div>
      {label && <div className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted">{label}</div>}
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={label}>
        {options.map((option) => {
          const active = option.id === value
          return (
            <button key={option.id} type="button" role="radio" aria-checked={active}
              onClick={() => onChange(option.id)}
              className={`min-h-10 rounded-full border px-4 text-sm font-semibold transition-colors ${
                active ? 'border-button bg-button text-button-text'
                  : 'border-line text-text hover:border-line-strong'}`}>
              {option.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function StatStrip({ items }: { items: { value: ReactNode; label: string }[] }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="rounded-2xl border border-line bg-raised px-4 py-3">
          <div className="text-2xl font-black leading-tight">{item.value}</div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{item.label}</div>
        </div>
      ))}
    </div>
  )
}

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-8">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-extrabold">{title}</h2>
        {aside && <div className="text-xs text-muted">{aside}</div>}
      </div>
      {children}
    </section>
  )
}

export function Photo({ src, size = 44 }: { src: string; size?: number }) {
  return <img src={src} alt="" width={size} height={size * 0.82} loading="lazy"
    className="shrink-0 object-contain object-bottom" style={{ width: size, height: size * 0.82 }} />
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-line px-5 py-8 text-center">
      <div className="font-bold">{title}</div>
      {hint && <div className="mt-1 text-sm text-muted">{hint}</div>}
    </div>
  )
}
