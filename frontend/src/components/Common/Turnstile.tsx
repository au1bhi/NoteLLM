import { useQuery } from "@tanstack/react-query"
import { RefreshCw, ShieldCheck } from "lucide-react"
import { useTheme } from "next-themes"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { authApi } from "@/services/auth"

interface TurnstileApi {
  render: (
    container: HTMLElement,
    options: {
      sitekey: string
      theme: "light" | "dark"
      language: string
      size: "flexible"
      callback: (token: string) => void
      "expired-callback": () => void
      "error-callback": () => void
      "timeout-callback": () => void
    },
  ) => string
  remove: (widgetId: string) => void
  reset: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

const SCRIPT_ID = "cloudflare-turnstile-script"
const SCRIPT_SRC =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
const SCRIPT_TIMEOUT_MS = 12_000
let scriptPromise: Promise<TurnstileApi> | null = null

function loadTurnstile(): Promise<TurnstileApi> {
  if (window.turnstile) return Promise.resolve(window.turnstile)
  if (scriptPromise) return scriptPromise

  scriptPromise = new Promise<TurnstileApi>((resolve, reject) => {
    const existing = document.getElementById(
      SCRIPT_ID,
    ) as HTMLScriptElement | null
    // A script without the global API is an orphan from a failed load or HMR.
    // Replace it so a visible retry always starts a fresh initialization.
    existing?.remove()
    const script = document.createElement("script")
    let settled = false

    const fail = (message: string) => {
      if (settled) return
      settled = true
      window.clearTimeout(timeoutId)
      script.remove()
      scriptPromise = null
      reject(new Error(message))
    }

    const onLoad = () => {
      if (settled) return
      if (!window.turnstile) {
        fail("安全验证脚本未正确初始化")
        return
      }
      settled = true
      window.clearTimeout(timeoutId)
      resolve(window.turnstile)
    }
    const onError = () => fail("安全验证加载失败")
    const timeoutId = window.setTimeout(
      () => fail("安全验证加载超时"),
      SCRIPT_TIMEOUT_MS,
    )

    script.addEventListener("load", onLoad, { once: true })
    script.addEventListener("error", onError, { once: true })
    script.id = SCRIPT_ID
    script.src = SCRIPT_SRC
    script.async = true
    script.defer = true
    document.head.appendChild(script)
  })
  return scriptPromise
}

export function useTurnstile() {
  const config = useQuery({
    queryKey: ["meta", "turnstile"],
    queryFn: authApi.getTurnstileConfig,
    retry: 1,
    staleTime: Number.POSITIVE_INFINITY,
  })
  const [token, setToken] = useState<string | null>(null)
  const [resetKey, setResetKey] = useState(0)
  const enabled = config.data?.enabled === true

  return {
    enabled,
    siteKey: config.data?.site_key?.trim() || null,
    token,
    setToken,
    resetKey,
    reset: () => {
      setToken(null)
      setResetKey((key) => key + 1)
    },
    canSubmit: config.isSuccess && (!enabled || Boolean(token)),
    // `isLoading` is false when an errored query is being refetched. Expose
    // `isFetching` so clicking the visible retry button immediately replaces
    // the error state with progress feedback and cannot look like a no-op.
    isLoading: config.isFetching,
    isError: config.isError,
    retryConfig: () => config.refetch(),
  }
}

interface TurnstileProps {
  enabled: boolean
  siteKey: string | null
  resetKey: number
  isLoading: boolean
  isError: boolean
  onTokenChange: (token: string | null) => void
  onRetryConfig: () => void
}

export function Turnstile({
  enabled,
  siteKey,
  resetKey,
  isLoading,
  isError,
  onTokenChange,
  onRetryConfig,
}: TurnstileProps) {
  const { resolvedTheme } = useTheme()
  const containerRef = useRef<HTMLFieldSetElement>(null)
  const widgetIdRef = useRef<string | null>(null)
  const onTokenChangeRef = useRef(onTokenChange)
  const previousResetKey = useRef(resetKey)
  const [widgetError, setWidgetError] = useState(false)
  const [widgetLoading, setWidgetLoading] = useState(false)
  const [renderAttempt, setRenderAttempt] = useState(0)
  const renderAttemptRef = useRef(renderAttempt)
  renderAttemptRef.current = renderAttempt

  useEffect(() => {
    onTokenChangeRef.current = onTokenChange
  }, [onTokenChange])

  useEffect(() => {
    if (!enabled || !siteKey || !containerRef.current) return
    let disposed = false
    let renderedWidgetId: string | null = null
    const currentAttempt = renderAttempt
    setWidgetError(false)
    setWidgetLoading(true)

    void loadTurnstile()
      .then((turnstile) => {
        if (disposed || !containerRef.current) return
        const isCurrentWidget = () =>
          !disposed && currentAttempt === renderAttemptRef.current
        renderedWidgetId = turnstile.render(containerRef.current, {
          sitekey: siteKey,
          theme: resolvedTheme === "dark" ? "dark" : "light",
          language: "zh-cn",
          size: "flexible",
          callback: (token) => {
            if (isCurrentWidget()) onTokenChangeRef.current(token)
          },
          "expired-callback": () => {
            if (isCurrentWidget()) onTokenChangeRef.current(null)
          },
          "error-callback": () => {
            if (!isCurrentWidget()) return
            onTokenChangeRef.current(null)
            setWidgetError(true)
          },
          "timeout-callback": () => {
            if (isCurrentWidget()) onTokenChangeRef.current(null)
          },
        })
        widgetIdRef.current = renderedWidgetId
        if (currentAttempt === renderAttemptRef.current) {
          setWidgetLoading(false)
        }
      })
      .catch(() => {
        if (!disposed && currentAttempt === renderAttemptRef.current) {
          setWidgetLoading(false)
          setWidgetError(true)
        }
      })

    return () => {
      disposed = true
      if (renderedWidgetId && window.turnstile) {
        try {
          window.turnstile.remove(renderedWidgetId)
        } catch {
          // The widget may already have removed itself after a challenge error.
        }
      }
      if (widgetIdRef.current === renderedWidgetId) widgetIdRef.current = null
      onTokenChangeRef.current(null)
    }
  }, [enabled, renderAttempt, resolvedTheme, siteKey])

  useEffect(() => {
    if (previousResetKey.current === resetKey) return
    previousResetKey.current = resetKey
    if (widgetIdRef.current && window.turnstile) {
      try {
        window.turnstile.reset(widgetIdRef.current)
      } catch {
        setWidgetError(true)
      }
    }
  }, [resetKey])

  if (isLoading) {
    return (
      <p
        className="flex min-h-12 items-center justify-center gap-2 rounded-md border bg-muted/30 px-3 text-xs text-muted-foreground"
        aria-live="polite"
      >
        <ShieldCheck className="size-4" />
        正在加载安全验证…
      </p>
    )
  }

  if (isError || (enabled && !siteKey)) {
    return (
      <div
        className="flex min-h-12 items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/5 px-3 text-xs text-destructive"
        role="alert"
      >
        <span>安全验证暂时不可用</span>
        <Button type="button" variant="ghost" size="sm" onClick={onRetryConfig}>
          <RefreshCw className="size-3.5" />
          重试
        </Button>
      </div>
    )
  }

  if (!enabled || !siteKey) return null

  if (widgetError) {
    return (
      <div
        className="flex min-h-12 items-center justify-between gap-3 rounded-md border border-destructive/40 bg-destructive/5 px-3 text-xs text-destructive"
        role="alert"
      >
        <span>安全验证加载失败</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setWidgetError(false)
            setRenderAttempt((attempt) => attempt + 1)
          }}
        >
          <RefreshCw className="size-3.5" />
          重试
        </Button>
      </div>
    )
  }

  return (
    <div
      className="relative -mx-4 min-h-[65px] w-[calc(100%+2rem)] min-w-0 sm:mx-0 sm:w-full"
      aria-busy={widgetLoading}
    >
      {widgetLoading && (
        <p
          className="absolute inset-0 flex items-center justify-center gap-2 rounded-md border bg-muted/30 px-3 text-xs text-muted-foreground"
          aria-live="polite"
        >
          <ShieldCheck className="size-4" />
          正在加载安全验证…
        </p>
      )}
      <fieldset
        ref={containerRef}
        className={`min-h-[65px] min-w-0 w-full overflow-hidden ${widgetLoading ? "invisible" : ""}`}
        aria-label="人机验证"
      />
    </div>
  )
}
