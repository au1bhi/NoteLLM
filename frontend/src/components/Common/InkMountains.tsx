import { useId } from "react"

interface InkMountainsProps {
  className?: string
}

/** Layered ink-wash mountain landscape with a mist band. Place on a dark
 * gradient surface so the translucent white ranges read as brush strokes. */
export function InkMountains({ className }: InkMountainsProps) {
  const mistId = useId()
  return (
    <svg
      viewBox="0 0 600 280"
      className={className}
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={mistId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="white" stopOpacity="0" />
          <stop offset="0.5" stopColor="white" stopOpacity="0.18" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </linearGradient>
      </defs>
      <rect y="120" width="600" height="100" fill={`url(#${mistId})`} />
      <path
        d="M0 200 C60 120 110 190 180 110 C250 60 300 180 360 90 C420 40 480 160 540 100 L600 140 L600 280 L0 280 Z"
        fill="rgba(255,255,255,0.1)"
        className="ink-draw"
      />
      <path
        d="M0 260 C70 190 140 250 220 170 C300 120 360 230 440 150 C500 110 550 190 600 160 L600 280 L0 280 Z"
        fill="rgba(255,255,255,0.18)"
        className="ink-draw"
      />
      <path
        d="M0 280 L0 250 C90 220 160 280 260 240 L340 270 L480 230 L600 260 L600 280 Z"
        fill="rgba(255,255,255,0.28)"
        className="ink-draw"
      />
    </svg>
  )
}
