import { AxiosError } from "axios"
import { ApiError } from "./client"

/**
 * Extract a user-facing error message, preferring the backend's Chinese
 * `detail` over the HTTP status phrase used by the generated client.
 */
export function extractErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const detail = (err.body as { detail?: unknown } | undefined)?.detail
    if (typeof detail === "string" && detail) return detail
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: unknown }
      if (typeof first?.msg === "string") return first.msg
    }
    if (err.status === 429) return "请求过于频繁，请稍后重试"
    if (err.status === 503) return "服务暂时不可用，请稍后重试"
    if (err.status >= 500) return "服务器暂时无法处理请求，请稍后重试"
  }
  if (err instanceof AxiosError) {
    if (err.code === "ECONNABORTED" || err.code === "ETIMEDOUT") {
      return "请求超时，请检查网络后重试"
    }
    if (err.code === "ERR_NETWORK" || !err.response) {
      return "网络连接失败，请检查网络后重试"
    }
    if (err.message) return err.message
  }
  if (err instanceof Error && err.message) {
    return err.message
  }
  return "出了点问题。"
}

export const handleError = function (
  this: (msg: string) => void,
  err: ApiError,
) {
  this(extractErrorMessage(err))
}

export const getInitials = (name: string): string => {
  return name
    .split(" ")
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase()
}

const TIME_INTERVALS = [
  { label: "年", seconds: 31536000 },
  { label: "个月", seconds: 2592000 },
  { label: "周", seconds: 604800 },
  { label: "天", seconds: 86400 },
  { label: "小时", seconds: 3600 },
  { label: "分钟", seconds: 60 },
] as const

export function timeAgo(dateInput: string | Date): string {
  const date = typeof dateInput === "string" ? new Date(dateInput) : dateInput
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return "刚刚"
  for (const { label, seconds: interval } of TIME_INTERVALS) {
    const count = Math.floor(seconds / interval)
    if (count >= 1) {
      return `${count}${label}前`
    }
  }
  return "刚刚"
}

export function sortPinnedFirst<T extends { is_pinned?: boolean }>(
  items: T[],
): T[] {
  return [...items].sort(
    (a, b) => Number(Boolean(b.is_pinned)) - Number(Boolean(a.is_pinned)),
  )
}
