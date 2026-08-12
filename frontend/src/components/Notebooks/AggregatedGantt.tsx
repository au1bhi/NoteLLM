import { Link } from "@tanstack/react-router"
import { useMemo } from "react"

import type { StudyPlanListItem, StudyTaskPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

import {
  AGGREGATED_DAY_WIDTH,
  dateLabel,
  dayOffset,
  difficultyLabels,
  localDateString,
  parseDate,
} from "./gantt"

const PLAN_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
] as const

interface AggregatedGanttProps {
  plans: StudyPlanListItem[]
}

function colorForNotebook(notebookId: string): string {
  let hash = 0
  for (const char of notebookId) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  }
  return PLAN_COLORS[hash % PLAN_COLORS.length]
}

function timelineBounds(plans: StudyPlanListItem[]): {
  start: string
  end: string
  duration: number
} {
  const start = plans.reduce(
    (earliest, plan) =>
      plan.start_date < earliest ? plan.start_date : earliest,
    plans[0].start_date,
  )
  const end = plans.reduce(
    (latest, plan) => (plan.end_date > latest ? plan.end_date : latest),
    plans[0].end_date,
  )
  return {
    start,
    end,
    duration: dayOffset(end, start) + 1,
  }
}

function TaskBar({
  task,
  origin,
  color,
}: {
  task: StudyTaskPublic
  origin: string
  color: string
}) {
  const start = dayOffset(task.start_date, origin)
  const span = dayOffset(task.end_date, task.start_date) + 1
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            "absolute top-2 h-8 min-w-7 rounded shadow-sm",
            task.is_completed && "opacity-45",
          )}
          style={{
            left: start * AGGREGATED_DAY_WIDTH + 2,
            width: Math.max(span * AGGREGATED_DAY_WIDTH - 4, 28),
            backgroundColor: color,
          }}
          aria-label={`${task.title}：${dateLabel(task.start_date)}—${dateLabel(task.end_date)}`}
        />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs space-y-1">
        <p className="font-medium">{task.title}</p>
        <p>
          {dateLabel(task.start_date)}—{dateLabel(task.end_date)}
        </p>
        <p>每天约 {task.estimated_minutes} 分钟</p>
        {task.is_completed ? <p>已完成</p> : null}
      </TooltipContent>
    </Tooltip>
  )
}

export function AggregatedGantt({ plans }: AggregatedGanttProps) {
  const { start, duration } = useMemo(() => timelineBounds(plans), [plans])
  const today = localDateString()
  const todayOffset = dayOffset(today, start)
  const showToday = todayOffset >= 0 && todayOffset < duration
  const days = Array.from({ length: duration }, (_, index) => index)
  const timelineWidth = duration * AGGREGATED_DAY_WIDTH
  const legendNotebooks = useMemo(() => {
    const seen = new Map<string, string>()
    for (const plan of plans) {
      if (!seen.has(plan.notebook_id)) {
        seen.set(plan.notebook_id, plan.notebook_title)
      }
    }
    return [...seen.entries()].map(([id, title]) => ({
      id,
      title,
      color: colorForNotebook(id),
    }))
  }, [plans])

  return (
    <div className="space-y-3">
      {legendNotebooks.length > 1 ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
          {legendNotebooks.map((notebook) => (
            <li key={notebook.id} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="size-2.5 rounded-sm"
                style={{ backgroundColor: notebook.color }}
              />
              <span>{notebook.title}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="overflow-x-auto rounded-xl border bg-muted/20">
        <div
          className="grid min-w-max"
          style={{ gridTemplateColumns: `13rem ${timelineWidth}px` }}
        >
          <div className="sticky left-0 z-10 border-b border-r bg-background px-3 py-2 text-xs font-medium">
            对话计划
          </div>
          <div className="relative flex border-b bg-background">
            {days.map((index) => {
              const current = new Date(
                parseDate(start).getTime() + index * 86_400_000,
              )
              return (
                <div
                  key={current.toISOString()}
                  className="shrink-0 border-r px-0.5 py-2 text-center text-[10px] text-muted-foreground"
                  style={{ width: AGGREGATED_DAY_WIDTH }}
                >
                  {current.getUTCMonth() + 1}/{current.getUTCDate()}
                </div>
              )
            })}
            {showToday ? (
              <div
                aria-hidden="true"
                className="pointer-events-none absolute inset-y-0 z-[1] w-px bg-primary"
                style={{
                  left:
                    todayOffset * AGGREGATED_DAY_WIDTH +
                    AGGREGATED_DAY_WIDTH / 2,
                }}
              />
            ) : null}
          </div>

          {plans.map((plan) => {
            const color = colorForNotebook(plan.notebook_id)
            return (
              <div key={plan.id} className="contents">
                <div className="sticky left-0 z-10 flex flex-col justify-center gap-0.5 border-r border-b bg-background px-3 py-2">
                  <Link
                    to="/notebooks/$notebookId"
                    params={{ notebookId: plan.notebook_id }}
                    search={{ conversation: plan.conversation_id }}
                    className="line-clamp-1 text-xs font-medium hover:underline"
                  >
                    {plan.title}
                  </Link>
                  <span className="line-clamp-1 text-[11px] text-muted-foreground">
                    {plan.notebook_title} · {plan.conversation_title}
                  </span>
                </div>
                <div
                  className="relative h-12 border-b"
                  style={{
                    backgroundImage:
                      "linear-gradient(to right, hsl(var(--border)) 1px, transparent 1px)",
                    backgroundSize: `${AGGREGATED_DAY_WIDTH}px 100%`,
                  }}
                >
                  {showToday ? (
                    <div
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-y-0 z-[1] w-px bg-primary/70"
                      style={{
                        left:
                          todayOffset * AGGREGATED_DAY_WIDTH +
                          AGGREGATED_DAY_WIDTH / 2,
                      }}
                    />
                  ) : null}
                  {plan.tasks.map((task) => (
                    <TaskBar
                      key={task.id}
                      task={task}
                      origin={start}
                      color={color}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <caption className="sr-only">全部学习计划任务</caption>
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">计划</th>
              <th className="px-3 py-2 font-medium">笔记本</th>
              <th className="px-3 py-2 font-medium">对话</th>
              <th className="px-3 py-2 font-medium">阶段</th>
              <th className="px-3 py-2 font-medium">日期</th>
              <th className="px-3 py-2 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            {plans.flatMap((plan) =>
              plan.tasks.map((task) => (
                <tr key={task.id} className="border-t">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span>{plan.title}</span>
                      <Badge variant="secondary" className="font-normal">
                        {difficultyLabels[plan.difficulty]}
                      </Badge>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {plan.notebook_title}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {plan.conversation_title}
                  </td>
                  <td className="px-3 py-2">{task.title}</td>
                  <td className="px-3 py-2 tabular-nums text-muted-foreground">
                    {dateLabel(task.start_date)}—{dateLabel(task.end_date)}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {task.is_completed ? "已完成" : "进行中"}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
