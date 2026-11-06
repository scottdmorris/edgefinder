// The shot chart: a full court in feet (94 x 50), the home team's floor and logo, and every shot
// at its team's own end (away shoots left, home right; the API already flips second-half shots).
// Made shots are filled dots, misses are crosses; shots new since the last refresh pop in.
import type { Shot } from '../lib/api'

const LENGTH = 94
const WIDTH = 50
const HOOP = 5.25
const THREE = 23.75
const CORNER = 3
const CORNER_X = HOOP + Math.sqrt(THREE ** 2 - (WIDTH / 2 - CORNER) ** 2)

function end(mirror: boolean) {
  const x = (v: number) => (mirror ? LENGTH - v : v)
  const sweep = mirror ? 0 : 1
  return (
    <g>
      <rect x={mirror ? LENGTH - 19 : 0} y={17} width={19} height={16} />
      <circle cx={x(19)} cy={WIDTH / 2} r={6} />
      <path d={`M${x(0)},${CORNER} L${x(CORNER_X)},${CORNER} A${THREE},${THREE} 0 0 ${sweep} ${x(CORNER_X)},${WIDTH - CORNER} L${x(0)},${WIDTH - CORNER}`} />
      <path d={`M${x(HOOP)},${WIDTH / 2 - 4} A4,4 0 0 ${sweep} ${x(HOOP)},${WIDTH / 2 + 4}`} />
      <line x1={x(4)} x2={x(4)} y1={22} y2={28} strokeWidth={0.5} />
      <circle cx={x(HOOP)} cy={WIDTH / 2} r={0.75} />
    </g>
  )
}

export function Court({ shots, colors, homeColor, homeLogo, freshFrom }: {
  shots: Shot[]
  colors: Record<string, string>
  homeColor: string
  homeLogo: string
  freshFrom: number | null // shots numbered above this arrived since the last refresh
}) {
  return (
    <svg viewBox={`-1 -1 ${LENGTH + 2} ${WIDTH + 2}`} className="w-full rounded-xl" role="img"
      aria-label={`Shot chart, ${shots.length} shots`}>
      <defs>
        <linearGradient id="floor" x1="0" x2="1">
          <stop offset="0" stopColor="#1a1712" />
          <stop offset="0.5" stopColor="#221d16" />
          <stop offset="1" stopColor="#1a1712" />
        </linearGradient>
      </defs>
      <rect x={-1} y={-1} width={LENGTH + 2} height={WIDTH + 2} fill="url(#floor)" rx={1.5} />
      <rect x={0} y={17} width={19} height={16} fill={homeColor} opacity={0.14} />
      <rect x={LENGTH - 19} y={17} width={19} height={16} fill={homeColor} opacity={0.14} />
      {homeLogo && <image href={homeLogo} x={LENGTH / 2 - 7} y={WIDTH / 2 - 7} width={14} height={14} opacity={0.18} />}
      <g fill="none" stroke="#e7e9ea" strokeOpacity={0.35} strokeWidth={0.3}>
        <rect x={0} y={0} width={LENGTH} height={WIDTH} />
        <line x1={LENGTH / 2} x2={LENGTH / 2} y1={0} y2={WIDTH} />
        <circle cx={LENGTH / 2} cy={WIDTH / 2} r={6} />
        {end(false)}
        {end(true)}
      </g>
      {shots.map((shot) => {
        const cx = (shot.x / 100) * LENGTH
        const cy = (shot.y / 100) * WIDTH
        const color = colors[shot.team] ?? '#e7e9ea'
        const fresh = freshFrom !== null && shot.n > freshFrom
        return (
          <g key={shot.n} className={fresh ? 'shot-pop' : undefined}>
            <title>{`${shot.text} · ${shot.period_label}`}</title>
            {shot.made
              ? <circle cx={cx} cy={cy} r={0.85} fill={color} stroke="#000" strokeWidth={0.15} />
              : <path d={`M${cx - 0.6},${cy - 0.6} L${cx + 0.6},${cy + 0.6} M${cx + 0.6},${cy - 0.6} L${cx - 0.6},${cy + 0.6}`}
                  stroke={color} strokeWidth={0.3} strokeOpacity={0.7} />}
          </g>
        )
      })}
    </svg>
  )
}
