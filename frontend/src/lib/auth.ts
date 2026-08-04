/**
 * Client-side session helpers. The JWT's `exp` claim is decoded locally (just
 * the base64url payload — signature verification stays on the server) so the
 * app can detect an expired session *before* any request round-trip and
 * redirect to the login page instantly, instead of rendering a dashboard that
 * looks usable but 401s on every request.
 */

const TOKEN_KEY = "access_token"

/** Key in sessionStorage that marks "redirected here because the session expired". */
export const AUTH_EXPIRED_KEY = "auth_session_expired"

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/** Decode the JWT payload and return its `exp` (epoch seconds), or null. */
export function decodeTokenExpiry(token: string): number | null {
  try {
    const payload = token.split(".")[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/")
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4)
    const json = new TextDecoder().decode(
      Uint8Array.from(atob(padded), (c) => c.charCodeAt(0)),
    )
    const claims = JSON.parse(json) as { exp?: unknown }
    return typeof claims.exp === "number" ? claims.exp : null
  } catch {
    return null
  }
}

/**
 * True when a token is present but expired (or unreadable). A missing token
 * returns false — "not logged in" is the caller's job, this only detects a
 * *stale* session. An unreadable `exp` counts as expired: the server would
 * reject the token anyway, and lingering on a fake-usable page is the exact
 * bug we're avoiding.
 */
export function isTokenExpired(): boolean {
  const token = getToken()
  if (!token) return false
  const exp = decodeTokenExpiry(token)
  return exp === null || exp * 1000 <= Date.now()
}
