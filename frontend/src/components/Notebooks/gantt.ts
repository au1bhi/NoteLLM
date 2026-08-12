import type { StudyPlanPublic } from "@/client"

export const DAY_WIDTH = 44
export const AGGREGATED_DAY_WIDTH = 32

export const difficultyLabels = {
  beginner: "入门",
  intermediate: "进阶",
  advanced: "挑战",
} as const

export function parseDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number)
  return new Date(Date.UTC(year, month - 1, day))
}

export function dayOffset(value: string, origin: string): number {
  return Math.round(
    (parseDate(value).getTime() - parseDate(origin).getTime()) / 86_400_000,
  )
}

export function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    timeZone: "UTC",
  }).format(parseDate(value))
}

export function planDuration(
  plan: Pick<StudyPlanPublic, "start_date" | "end_date">,
): number {
  return dayOffset(plan.end_date, plan.start_date) + 1
}

export function localDateString(date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}
