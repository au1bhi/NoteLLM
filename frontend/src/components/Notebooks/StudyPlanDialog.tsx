import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CalendarRange,
  CheckCircle2,
  Clock3,
  Loader2,
  Mail,
  RefreshCw,
  Sparkles,
} from "lucide-react"
import { useState } from "react"

import {
  type StudyPlanPublic,
  StudyPlansService,
  type StudyTaskPublic,
} from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { extractErrorMessage } from "@/utils"

const DAY_WIDTH = 44
const difficultyLabels = {
  beginner: "入门",
  intermediate: "进阶",
  advanced: "挑战",
} as const

function parseDate(value: string): Date {
  const [year, month, day] = value.split("-").map(Number)
  return new Date(Date.UTC(year, month - 1, day))
}

function dayOffset(value: string, origin: string): number {
  return Math.round(
    (parseDate(value).getTime() - parseDate(origin).getTime()) / 86_400_000,
  )
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    timeZone: "UTC",
  }).format(parseDate(value))
}

function planDuration(plan: StudyPlanPublic): number {
  return dayOffset(plan.end_date, plan.start_date) + 1
}

function GanttChart({ plan }: { plan: StudyPlanPublic }) {
  const duration = planDuration(plan)
  const timelineWidth = duration * DAY_WIDTH
  const days = Array.from({ length: duration }, (_, index) => index)

  return (
    <div className="overflow-x-auto rounded-xl border bg-muted/20">
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

interface TaskListProps {
  plan: StudyPlanPublic
  pendingTaskId: string | null
  onToggle: (task: StudyTaskPublic, completed: boolean) => void
}

function TaskList({ plan, pendingTaskId, onToggle }: TaskListProps) {
  return (
    <div className="space-y-2">
      {plan.tasks.map((task) => (
        <label
          key={task.id}
          htmlFor={`study-task-${task.id}`}
          className="flex cursor-pointer gap-3 rounded-lg border bg-background p-3"
        >
          <Checkbox
            id={`study-task-${task.id}`}
            className="mt-0.5"
            checked={task.is_completed}
            disabled={pendingTaskId === task.id}
            onCheckedChange={(checked) => onToggle(task, checked === true)}
          />
          <span className="min-w-0 flex-1">
            <span
              className={cn(
                "block text-sm font-medium",
                task.is_completed && "text-muted-foreground line-through",
              )}
            >
              {task.title}
            </span>
            <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">
              {task.description}
            </span>
            <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
              <span>
                {dateLabel(task.start_date)}—{dateLabel(task.end_date)}
              </span>
              <span className="flex items-center gap-1">
                <Clock3 className="size-3" /> 每天约 {task.estimated_minutes}{" "}
                分钟
              </span>
            </span>
          </span>
        </label>
      ))}
    </div>
  )
}

interface StudyPlanDialogProps {
  conversationId: string
  hasConversationContent: boolean
  disabled?: boolean
}

export function StudyPlanDialog({
  conversationId,
  hasConversationContent,
  disabled,
}: StudyPlanDialogProps) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const queryKey = ["study-plan", conversationId]

  const planQuery = useQuery({
    queryKey,
    queryFn: () =>
      StudyPlansService.readConversationStudyPlan({ conversationId }),
    enabled: open,
  })
  const generateMutation = useMutation({
    mutationFn: () =>
      StudyPlansService.createOrRegenerateStudyPlan({
        conversationId,
        requestBody: {
          timezone:
            Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai",
        },
      }),
    onSuccess: (plan) => {
      queryClient.setQueryData(queryKey, plan)
      showSuccessToast("学习计划与甘特图已生成")
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })
  const reminderMutation = useMutation({
    mutationFn: ({ planId, enabled }: { planId: string; enabled: boolean }) =>
      StudyPlansService.updateStudyPlan({
        planId,
        requestBody: { reminder_enabled: enabled },
      }),
    onSuccess: (plan) => {
      queryClient.setQueryData(queryKey, plan)
      showSuccessToast(
        plan.reminder_enabled ? "每天 9:00 邮件提醒已开启" : "邮件提醒已关闭",
      )
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })
  const taskMutation = useMutation({
    mutationFn: ({
      planId,
      task,
      completed,
    }: {
      planId: string
      task: StudyTaskPublic
      completed: boolean
    }) =>
      StudyPlansService.updateStudyTask({
        planId,
        taskId: task.id,
        requestBody: { is_completed: completed },
      }),
    onSuccess: (updatedTask) => {
      queryClient.setQueryData<StudyPlanPublic | null>(queryKey, (plan) =>
        plan
          ? {
              ...plan,
              tasks: plan.tasks.map((task) =>
                task.id === updatedTask.id ? updatedTask : task,
              ),
            }
          : plan,
      )
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const plan = planQuery.data
  const completed = plan?.tasks.filter((task) => task.is_completed).length ?? 0

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 shrink-0 rounded-md text-muted-foreground hover:text-foreground"
          disabled={disabled}
          aria-label="学习计划与甘特图"
          title="学习计划与甘特图"
        >
          <CalendarRange className="size-3.5" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarRange className="size-5 text-primary" />
            学习计划与甘特图
          </DialogTitle>
          <DialogDescription>
            从当前会话提炼目标，自动判断难度并安排学习周期。计划仅在你主动开启后发送邮件提醒。
          </DialogDescription>
        </DialogHeader>

        {planQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 rounded-xl" />
            <Skeleton className="h-56 rounded-xl" />
          </div>
        ) : null}
        {planQuery.error ? (
          <p className="text-sm text-destructive">
            {extractErrorMessage(planQuery.error)}
          </p>
        ) : null}
        {!planQuery.isLoading && !plan ? (
          <div className="rounded-xl border border-dashed p-8 text-center">
            <Sparkles className="mx-auto size-8 text-primary" />
            <p className="mt-3 font-medium">把对话变成可执行的学习周期</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              系统会分析对话主题与目标，生成 3—60
              天的阶段任务、每日建议时长和验收方式。
            </p>
            <Button
              className="mt-4"
              disabled={!hasConversationContent || generateMutation.isPending}
              onClick={() => generateMutation.mutate()}
            >
              {generateMutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Sparkles className="size-4" />
              )}
              生成学习计划
            </Button>
            {!hasConversationContent ? (
              <p className="mt-2 text-xs text-muted-foreground">
                当前会话有内容后才能生成。
              </p>
            ) : null}
          </div>
        ) : null}

        {plan ? (
          <div className="space-y-5">
            <div className="rounded-xl border bg-card p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-semibold">{plan.title}</h3>
                    <Badge variant="secondary">
                      {difficultyLabels[plan.difficulty]}
                    </Badge>
                    <Badge variant="outline">{planDuration(plan)} 天</Badge>
                  </div>
                  <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
                    {plan.summary}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    generateMutation.isPending || !hasConversationContent
                  }
                  onClick={() => generateMutation.mutate()}
                >
                  <RefreshCw
                    className={cn(
                      "size-3.5",
                      generateMutation.isPending && "animate-spin",
                    )}
                  />
                  重新生成
                </Button>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                <span>
                  周期：{plan.start_date}—{plan.end_date}
                </span>
                <span>
                  进度：{completed}/{plan.tasks.length} 个阶段
                </span>
                <span>时区：{plan.timezone}</span>
              </div>
            </div>

            <section>
              <h3 className="mb-2 text-sm font-semibold">甘特图</h3>
              <GanttChart plan={plan} />
            </section>

            <section className="rounded-xl border bg-muted/20 p-4">
              <div className="flex items-start gap-3">
                <Mail className="mt-0.5 size-5 text-primary" />
                <div className="min-w-0 flex-1">
                  <label
                    htmlFor={`study-reminder-${plan.id}`}
                    className="flex cursor-pointer items-center gap-2 text-sm font-medium"
                  >
                    <Checkbox
                      id={`study-reminder-${plan.id}`}
                      checked={plan.reminder_enabled}
                      disabled={
                        reminderMutation.isPending ||
                        (!plan.email_reminder_available &&
                          !plan.reminder_enabled)
                      }
                      onCheckedChange={(checked) =>
                        reminderMutation.mutate({
                          planId: plan.id,
                          enabled: checked === true,
                        })
                      }
                    />
                    每天上午 {plan.reminder_time || "09:00"} 邮件提醒
                  </label>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {plan.email_reminder_available
                      ? "发送当日未完成任务到已验证邮箱，可随时关闭。"
                      : "邮箱未验证或服务器未配置邮件服务，因此暂不能开启。请先在设置中完成邮箱验证。"}
                  </p>
                </div>
              </div>
            </section>

            <section>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <CheckCircle2 className="size-4 text-primary" />
                详细计划
              </h3>
              <TaskList
                plan={plan}
                pendingTaskId={
                  taskMutation.isPending
                    ? (taskMutation.variables?.task.id ?? null)
                    : null
                }
                onToggle={(task, completed) =>
                  taskMutation.mutate({
                    planId: plan.id,
                    task,
                    completed,
                  })
                }
              />
            </section>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
