import type { StudyPlanPublic } from "@/client"
import { cn } from "@/lib/utils"

import {
  DAY_WIDTH,
  dateLabel,
  dayOffset,
  parseDate,
  planDuration,
} from "./gantt"

export function GanttChart({ plan }: { plan: StudyPlanPublic }) {
  const duration = planDuration(plan)
  const timelineWidth = duration * DAY_WIDTH
  const days = Array.from({ length: duration }, (_, index) => index)

  return (
    <div className="isolate max-w-full overflow-x-auto rounded-xl border bg-muted/20">
      <div
        className="grid min-w-max"
        style={{ gridTemplateColumns: `10rem ${timelineWidth}px` }}
      >
        <div className="sticky left-0 z-10 border-b border-r bg-background px-3 py-2 text-xs font-medium">
          学习阶段
        </div>
        <div className="flex border-b bg-background">
          {days.map((index) => {
            const current = new Date(
              parseDate(plan.start_date).getTime() + index * 86_400_000,
            )
            return (
              <div
                key={current.toISOString()}
                className="shrink-0 border-r px-1 py-2 text-center text-[11px] text-muted-foreground"
                style={{ width: DAY_WIDTH }}
              >
                {current.getUTCMonth() + 1}/{current.getUTCDate()}
              </div>
            )
          })}
        </div>
        {plan.tasks.map((task) => {
          const start = dayOffset(task.start_date, plan.start_date)
          const span = dayOffset(task.end_date, task.start_date) + 1
          return (
            <div key={task.id} className="contents">
              <div className="sticky left-0 z-10 flex items-center border-r border-b bg-background px-3 py-2">
                <span
                  className={cn(
                    "line-clamp-2 text-xs font-medium",
                    task.is_completed && "text-muted-foreground line-through",
                  )}
                >
                  {task.title}
                </span>
              </div>
              <div
                className="relative h-12 border-b"
                style={{
                  backgroundImage:
                    "linear-gradient(to right, hsl(var(--border)) 1px, transparent 1px)",
                  backgroundSize: `${DAY_WIDTH}px 100%`,
                }}
              >
                <div
                  className={cn(
                    "absolute top-2 flex h-8 items-center rounded-md px-2 text-[11px] font-medium shadow-sm",
                    task.is_completed
                      ? "bg-primary/25 text-muted-foreground"
                      : "bg-primary text-primary-foreground",
                  )}
                  style={{
                    left: start * DAY_WIDTH + 4,
                    width: Math.max(span * DAY_WIDTH - 8, 28),
                  }}
                  title={`${task.title}：${dateLabel(task.start_date)}—${dateLabel(task.end_date)}`}
                >
                  <span className="truncate">{task.title}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
