import { Link } from "@tanstack/react-router"

import { cn } from "@/lib/utils"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
  monochrome?: boolean
}

function Mark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-xl bg-brand-gradient shadow-soft",
        className,
      )}
    >
      <svg
        viewBox="0 0 24 24"
        className="size-[58%] text-white"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.9}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M12 6.3c-1.85-1.35-4.65-1.72-7.65-1.28v12.1c3-.44 5.8-.06 7.65 1.28 1.85-1.34 4.65-1.72 7.65-1.28V5.02C16.65 4.58 13.85 4.95 12 6.3Z" />
        <path d="M12 6.3v12.1" />
        <path
          d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"
          fill="currentColor"
          stroke="none"
          transform="translate(11.6 0.6) scale(0.4)"
        />
      </svg>
    </span>
  )
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
  monochrome = false,
}: LogoProps) {
  const content = (
    <span
      className={cn(
        "inline-flex items-center gap-2.5",
        variant === "responsive" &&
          "group-data-[collapsible=icon]:justify-center",
        className,
      )}
    >
      <Mark className={variant === "full" ? "size-8" : "size-7"} />
      {variant !== "icon" ? (
        <span
          className={cn(
            "text-[17px] font-semibold tracking-tight",
            variant === "responsive" && "group-data-[collapsible=icon]:hidden",
            monochrome && "text-white",
          )}
        >
          {monochrome ? (
            "NoteLLM"
          ) : (
            <>
              Note<span className="text-gradient">LLM</span>
            </>
          )}
        </span>
      ) : null}
    </span>
  )

  if (!asLink) {
    return content
  }

  return <Link to="/">{content}</Link>
}
