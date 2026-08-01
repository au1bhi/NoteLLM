import { Pin } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface PinButtonProps {
  pinned: boolean
  disabled?: boolean
  ariaLabel?: string
  className?: string
  onToggle: () => void
}

export function PinButton({
  pinned,
  disabled,
  ariaLabel,
  className,
  onToggle,
}: PinButtonProps) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className={className}
      disabled={disabled}
      aria-label={ariaLabel ?? (pinned ? "取消置顶" : "置顶")}
      onClick={(event) => {
        event.stopPropagation()
        onToggle()
      }}
    >
      <Pin className={cn("size-4", pinned && "fill-primary text-primary")} />
    </Button>
  )
}
