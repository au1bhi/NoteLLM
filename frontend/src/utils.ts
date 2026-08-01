import { AxiosError } from "axios"
import type { ApiError } from "./client"

function extractErrorMessage(err: ApiError): string {
  if (err instanceof AxiosError) {
    return err.message
  }

  const errDetail = (err.body as any)?.detail
  if (Array.isArray(errDetail) && errDetail.length > 0) {
    return errDetail[0].msg
  }
  return errDetail || "出了点问题。"
}

export const handleError = function (
  this: (msg: string) => void,
  err: ApiError,
) {
  const errorMessage = extractErrorMessage(err)
  this(errorMessage)
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
