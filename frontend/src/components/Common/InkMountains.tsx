import { useId } from "react"

interface InkMountainsProps {
  className?: string
}

/** Layered ink-wash mountain landscape with a mist band and a vermilion
 * painter's seal. Place on a dark gradient surface so the translucent white
 * ranges read as brush strokes. */
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
      <g className="animate-rise">
        <path
          d="M0 200 C60 120 110 190 180 110 C250 60 300 180 360 90 C420 40 480 160 540 100 L600 140 L600 280 L0 280 Z"
          fill="rgba(255,255,255,0.1)"
        />
        <path
          d="M0 260 C70 190 140 250 220 170 C300 120 360 230 440 150 C500 110 550 190 600 160 L600 280 L0 280 Z"
          fill="rgba(255,255,255,0.18)"
        />
        <path
          d="M0 280 L0 250 C90 220 160 280 260 240 L340 270 L480 230 L600 260 L600 280 Z"
          fill="rgba(255,255,255,0.28)"
        />
        <path
          d="M0 280 L0 265 C120 250 200 280 330 258 L480 280 Z"
          fill="rgba(255,255,255,0.42)"
        />
        {/* Vermilion painter's seal (落款) in the bottom-right corner. */}
        <g transform="translate(544 248)">
          <rect
            x="0"
            y="0"
            width="36"
            height="36"
            rx="7"
            fill="oklch(0.66 0.17 32)"
          />
          <path
            d="M18 9l2.3 6.6L27 18l-6.7 2.4L18 27l-2.3-6.6L9 18l6.7-2.4z"
            fill="oklch(0.99 0.01 85)"
          />
        </g>
      </g>
    </svg>
  )
}
