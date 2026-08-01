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
        "relative inline-flex shrink-0 items-center justify-center rounded-xl bg-brand-gradient shadow-soft",
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
      </svg>
      <span
        aria-hidden="true"
        className="absolute -bottom-1 -right-1 inline-flex size-[34%] items-center justify-center rounded-[35%] bg-[oklch(0.55_0.19_32)] ring-2 ring-card"
      >
        <svg
          viewBox="0 0 24 24"
          className="size-[62%] text-[oklch(0.99_0.01_85)]"
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M12 3l2.1 6.9L21 12l-6.9 2.1L12 21l-2.1-6.9L3 12l6.9-2.1z" />
        </svg>
      </span>
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
          "group-data-[collapsible=icon]:w-full group-data-[collapsible=icon]:justify-center",
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
