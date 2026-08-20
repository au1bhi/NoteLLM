import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Pencil } from "lucide-react"
import { useMemo, useState } from "react"

import type { StudyPlanListItem, StudyTaskPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { conversationsApi } from "@/services/conversations"
import { studyPlansApi } from "@/services/study-plans"
import { extractErrorMessage } from "@/utils"

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
  notebookId,
  conversationId,
}: {
  task: StudyTaskPublic
  origin: string
  color: string
  notebookId: string
  conversationId: string
}) {
  const start = dayOffset(task.start_date, origin)
  const span = dayOffset(task.end_date, task.start_date) + 1
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          to="/notebooks/$notebookId"
          params={{ notebookId }}
          search={{ conversation: conversationId }}
          className={cn(
            "absolute top-2 h-8 min-w-7 rounded shadow-sm transition-opacity",
            task.is_completed && "opacity-45 line-through",
          )}
          style={{
            left: start * AGGREGATED_DAY_WIDTH + 2,
            width: Math.max(span * AGGREGATED_DAY_WIDTH - 4, 28),
            backgroundColor: color,
          }}
          aria-label={`${task.title}：${dateLabel(task.start_date)}—${dateLabel(task.end_date)}，打开对应会话`}
        />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs space-y-1">
        <p className="font-medium">{task.title}</p>
        <p>
          {dateLabel(task.start_date)}—{dateLabel(task.end_date)}
        </p>
        <p>每天约 {task.estimated_minutes} 分钟</p>
        <p className="font-medium text-primary">
          {task.is_completed ? "✓ 已完成" : "⏳ 进行中"}
        </p>
        <p className="text-[11px] text-muted-foreground">点击打开对应会话</p>
      </TooltipContent>
    </Tooltip>
  )
}

export function AggregatedGantt({ plans }: AggregatedGanttProps) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const [renameTarget, setRenameTarget] = useState<{
    conversationId: string
    currentTitle: string
  } | null>(null)
  const [newTitle, setNewTitle] = useState("")

  const openRename = (conversationId: string, currentTitle: string) => {
    setRenameTarget({ conversationId, currentTitle })
    setNewTitle(currentTitle)
  }

  const renameMutation = useMutation({
    mutationFn: ({
      conversationId,
      title,
    }: {
      conversationId: string
      title: string
    }) => conversationsApi.update(conversationId, { title }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["study-plans"] })
      void queryClient.invalidateQueries({ queryKey: ["conversations"] })
      void queryClient.invalidateQueries({ queryKey: ["notebooks"] })
      showSuccessToast("对话已重命名")
      setRenameTarget(null)
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const taskMutation = useMutation({
    mutationFn: ({
      planId,
      taskId,
      completed,
    }: {
      planId: string
      taskId: string
      completed: boolean
    }) => studyPlansApi.updateTask(planId, taskId, { is_completed: completed }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["study-plans"] })
      void queryClient.invalidateQueries({ queryKey: ["study-plan"] })
      showSuccessToast("任务状态已更新")
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

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

      <div className="isolate overflow-x-auto rounded-xl border bg-muted/20">
        <div
          className="grid min-w-max"
          style={{ gridTemplateColumns: `14rem ${timelineWidth}px` }}
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
                <div className="sticky left-0 z-10 flex flex-col justify-center gap-1 border-r border-b bg-background px-3 py-2">
                  <Link
                    to="/notebooks/$notebookId"
                    params={{ notebookId: plan.notebook_id }}
                    search={{ conversation: plan.conversation_id }}
                    className="line-clamp-1 text-xs font-medium hover:text-primary hover:underline transition-colors"
                    title={`打开计划：${plan.title}`}
                  >
                    {plan.title}
                  </Link>
                  <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Link
                      to="/notebooks/$notebookId"
                      params={{ notebookId: plan.notebook_id }}
                      className="truncate hover:text-foreground hover:underline transition-colors"
                      title={`笔记本：${plan.notebook_title}`}
                    >
                      {plan.notebook_title}
                    </Link>
                    <span>·</span>
                    <Link
                      to="/notebooks/$notebookId"
                      params={{ notebookId: plan.notebook_id }}
                      search={{ conversation: plan.conversation_id }}
                      className="truncate hover:text-primary hover:underline transition-colors"
                      title={`对话：${plan.conversation_title}`}
                    >
                      {plan.conversation_title}
                    </Link>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-4 shrink-0 rounded p-0 text-muted-foreground/70 hover:text-foreground"
                      aria-label={`重命名对话：${plan.conversation_title}`}
                      title="重命名对话"
                      onClick={() =>
                        openRename(
                          plan.conversation_id,
                          plan.conversation_title,
                        )
                      }
                    >
                      <Pencil className="size-2.5" />
                    </Button>
                  </div>
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
                      notebookId={plan.notebook_id}
                      conversationId={plan.conversation_id}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <div className="isolate overflow-x-auto rounded-xl border">
        <table className="w-full min-w-[44rem] text-left text-sm">
          <caption className="sr-only">全部学习计划任务</caption>
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2.5 font-medium">计划</th>
              <th className="px-3 py-2.5 font-medium">笔记本</th>
              <th className="px-3 py-2.5 font-medium">对话</th>
              <th className="px-3 py-2.5 font-medium">阶段</th>
              <th className="px-3 py-2.5 font-medium">日期</th>
              <th className="px-3 py-2.5 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            {plans.flatMap((plan) =>
              plan.tasks.map((task) => (
                <tr key={task.id} className="border-t">
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <Link
                        to="/notebooks/$notebookId"
                        params={{ notebookId: plan.notebook_id }}
                        search={{ conversation: plan.conversation_id }}
                        className="font-medium hover:text-primary hover:underline transition-colors"
                        title="打开该计划对应的问答会话"
                      >
                        {plan.title}
                      </Link>
                      <Badge variant="secondary" className="font-normal">
                        {difficultyLabels[plan.difficulty]}
                      </Badge>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    <Link
                      to="/notebooks/$notebookId"
                      params={{ notebookId: plan.notebook_id }}
                      className="hover:text-foreground hover:underline transition-colors"
                      title="打开笔记本"
                    >
                      {plan.notebook_title}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    <div className="flex items-center gap-1.5">
                      <Link
                        to="/notebooks/$notebookId"
                        params={{ notebookId: plan.notebook_id }}
                        search={{ conversation: plan.conversation_id }}
                        className="text-foreground hover:text-primary hover:underline transition-colors"
                        title="跳转到该会话"
                      >
                        {plan.conversation_title}
                      </Link>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-6 shrink-0 rounded text-muted-foreground hover:text-foreground"
                        aria-label={`重命名对话：${plan.conversation_title}`}
                        title="重命名对话"
                        onClick={() =>
                          openRename(
                            plan.conversation_id,
                            plan.conversation_title,
                          )
                        }
                      >
                        <Pencil className="size-3" />
                      </Button>
                    </div>
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={cn(
                        task.is_completed &&
                          "text-muted-foreground line-through",
                      )}
                    >
                      {task.title}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 tabular-nums text-muted-foreground">
                    {dateLabel(task.start_date)}—{dateLabel(task.end_date)}
                  </td>
                  <td className="px-3 py-2.5">
                    <label
                      htmlFor={`task-check-${task.id}`}
                      className="inline-flex cursor-pointer items-center gap-2"
                    >
                      <Checkbox
                        id={`task-check-${task.id}`}
                        checked={task.is_completed}
                        disabled={
                          taskMutation.isPending &&
                          taskMutation.variables?.taskId === task.id
                        }
                        onCheckedChange={(checked) =>
                          taskMutation.mutate({
                            planId: plan.id,
                            taskId: task.id,
                            completed: checked === true,
                          })
                        }
                      />
                      <span
                        className={cn(
                          "text-xs select-none",
                          task.is_completed
                            ? "text-muted-foreground line-through"
                            : "font-medium text-foreground",
                        )}
                      >
                        {task.is_completed ? "已完成" : "进行中"}
                      </span>
                    </label>
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>

      <Dialog
        open={Boolean(renameTarget)}
        onOpenChange={(open) => {
          if (!open) setRenameTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>重命名对话</DialogTitle>
            <DialogDescription>
              修改此会话在笔记本与甘特图中的展示名称。
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              const trimmed = newTitle.trim()
              if (!trimmed || !renameTarget || renameMutation.isPending) return
              renameMutation.mutate({
                conversationId: renameTarget.conversationId,
                title: trimmed,
              })
            }}
            className="space-y-4"
          >
            <Input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="输入新的对话名称"
              maxLength={100}
              autoFocus
            />
            <DialogFooter className="gap-2 sm:gap-0">
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  取消
                </Button>
              </DialogClose>
              <Button
                type="submit"
                disabled={
                  !newTitle.trim() ||
                  newTitle.trim() === renameTarget?.currentTitle ||
                  renameMutation.isPending
                }
              >
                {renameMutation.isPending ? "保存中…" : "保存"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
