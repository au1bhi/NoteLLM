import { useQuery } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { CalendarRange } from "lucide-react"

import { AggregatedGantt } from "@/components/Notebooks/AggregatedGantt"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { studyPlansApi } from "@/services/study-plans"
import { extractErrorMessage } from "@/utils"

export const Route = createFileRoute("/_layout/gantt")({
  component: GanttPage,
  head: () => ({ meta: [{ title: "甘特图 - NoteLLM" }] }),
})

function GanttPage() {
  const { data, error, isLoading } = useQuery({
    queryFn: () => studyPlansApi.list(),
    queryKey: ["study-plans"],
  })

  const plans = data?.data ?? []

  return (
    <div className="isolate flex min-w-0 max-w-full flex-col gap-6 overflow-hidden">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">
          甘特图
        </h1>
        <p className="mt-1 text-muted-foreground">
          把所有对话里的学习计划放到同一条时间轴上，按笔记本着色，并跳回对应会话。
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-16 rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      ) : null}
      {error ? (
        <p className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {extractErrorMessage(error)}
        </p>
      ) : null}

      {!isLoading && !error && plans.length ? (
        <AggregatedGantt plans={plans} />
      ) : null}

      {!isLoading && !error && plans.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed px-6 py-16 text-center">
          <span className="inline-flex size-14 items-center justify-center rounded-2xl bg-brand-gradient-soft text-primary">
            <CalendarRange className="size-7" />
          </span>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">
              还没有可聚合的学习甘特图
            </h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              这里只聚合已有计划，不会自己生成。打开任意会话，点标题旁的「学习计划」，即可从对话生成甘特图。
            </p>
          </div>
          <Button asChild>
            <Link to="/notebooks">去笔记本打开会话</Link>
          </Button>
        </div>
      ) : null}
    </div>
  )
}
