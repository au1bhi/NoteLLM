import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { ApiError, OpenAPI } from "./client"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "@fontsource-variable/geist"
import "@fontsource-variable/geist-mono"
import "@fontsource-variable/noto-serif-sc"
import "./index.css"
import {
  AUTH_EXPIRED_KEY,
  clearToken,
  getToken,
  isTokenExpired,
} from "./lib/auth"
import { routeTree } from "./routeTree.gen"

OpenAPI.BASE = import.meta.env.VITE_API_URL ?? ""
OpenAPI.TOKEN = async () => getToken() ?? ""

const AUTH_REQUEST_TIMEOUT_MS = 15_000
const AUTH_REQUEST_PATHS = [
  "/api/v1/login/access-token",
  "/api/v1/users/signup",
  "/api/v1/password-recovery/",
  "/api/v1/reset-password/",
  "/api/v1/meta/turnstile",
  "/api/v1/users/verify-email",
  "/api/v1/users/resend-verification",
  "/api/v1/users/me/resend-verification",
]

OpenAPI.interceptors.request.use((config) => {
  const url = config.url ?? ""
  if (!AUTH_REQUEST_PATHS.some((path) => url.includes(path))) return config
  return { ...config, timeout: AUTH_REQUEST_TIMEOUT_MS }
})

OpenAPI.interceptors.response.use((response) => {
  if (response.status !== 429) return response

  const retryAfterHeader = response.headers["retry-after"]
  const retryAfter =
    typeof retryAfterHeader === "string"
      ? Number.parseInt(retryAfterHeader, 10)
      : Number.NaN
  const body = response.data
  if (
    !Number.isFinite(retryAfter) ||
    retryAfter <= 0 ||
    typeof body !== "object" ||
    body === null ||
    !("detail" in body) ||
    typeof body.detail !== "string"
  ) {
    return response
  }

  response.data = {
    ...body,
    detail: `${body.detail} 请在 ${retryAfter} 秒后重试。`,
  }
  return response
})

// An expired token at startup is the "fake offline" bug: the dashboard renders
// as if usable while every request 401s and only redirects to /login after
// retries. Clear it before the first render so `_layout.beforeLoad` redirects
// straight to the login page with a reason.
if (isTokenExpired()) {
  clearToken()
  sessionStorage.setItem(AUTH_EXPIRED_KEY, "1")
}

let redirectingToLogin = false
const redirectToLogin = (expired: boolean) => {
  // If we already are on a public route there is nothing to kick from.
  if (
    [
      "/login",
      "/signup",
      "/recover-password",
      "/reset-password",
      "/verify-email",
    ].includes(window.location.pathname)
  ) {
    clearToken()
    return
  }
  if (redirectingToLogin) return
  redirectingToLogin = true
  clearToken()
  if (expired) sessionStorage.setItem(AUTH_EXPIRED_KEY, "1")
  window.location.href = "/login"
  // Coalesce concurrent 401s from parallel page-load queries; later
  // expirations (next session) must be able to redirect again.
  window.setTimeout(() => {
    redirectingToLogin = false
  }, 1500)
}

const isAuthFailure = (error: Error) =>
  error instanceof ApiError && (error.status === 401 || error.status === 403)

const shouldRetryQuery = (failureCount: number, error: Error) => {
  if (isAuthFailure(error)) return false
  if (error instanceof ApiError && error.status === 429) return false
  return failureCount < 3
}

const handleApiError = (error: Error) => {
  if (isAuthFailure(error)) redirectToLogin(true)
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
  defaultOptions: {
    queries: {
      // Auth failures and 429 responses must not be replayed. Other transient
      // query failures keep the library's normal three-retry ceiling.
      retry: shouldRetryQuery,
    },
  },
})

const checkExpiredSession = () => {
  if (getToken() && isTokenExpired()) {
    redirectToLogin(true)
  }
}

// Kick an open tab the moment its session lapses, and immediately when the
// user comes back to it after being away — a stale page should never look
// usable even before any request happens.
window.setInterval(checkExpiredSession, 30_000)
window.addEventListener("focus", checkExpiredSession)
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") checkExpiredSession()
})

const router = createRouter({ routeTree })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
