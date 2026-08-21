import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  AlertCircle,
  ArrowUpDown,
  Bot,
  Calendar,
  CheckCircle2,
  Clock,
  Filter,
  ListOrdered,
  MoreHorizontal,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react"
import { useMemo, useState } from "react"

import type {
  StudyPlanListItem,
  StudyPlanUpdate,
  StudyTaskCreate,
  StudyTaskPublic,
  StudyTaskUpdate,
} from "@/client"
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
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

const DIFFICULTY_WEIGHT: Record<string, number> = {
  beginner: 1,
  intermediate: 2,
  advanced: 3,
}

const AI_PROMPT_PRESETS = [
  {
    label: "🚀 压缩周期提速",
    prompt: "将整个学习周期压缩紧凑，加大每日核心知识密度，缩短总天数。",
  },
  {
    label: "⏳ 排期顺延 7 天",
    prompt: "因近期有其他安排，将所有待完成任务整体顺延 7 天开始。",
  },
  {
    label: "🎯 增加实战演练",
    prompt: "增加更多实战操作与可交付成果验收阶段，提升实践难度。",
  },
  {
    label: "💡 降低每日负担",
    prompt: "将每日学习时长控制在 30 分钟以内，任务拆解更细致更平缓。",
  },
  {
    label: "🔄 增加巩固复习",
    prompt: "在关键节点增加阶段性知识点主动回忆与模拟自测任务。",
  },
]

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
  if (plans.length === 0) {
    const now = localDateString()
    return { start: now, end: now, duration: 1 }
  }
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
    duration: Math.max(dayOffset(end, start) + 1, 1),
  }
}

interface EnrichedTask extends StudyTaskPublic {
  planId: string
  planTitle: string
  planDifficulty: string
  notebookId: string
  notebookTitle: string
  conversationId: string
  color: string
}

function getTaskRelativeStatus(task: StudyTaskPublic, today: string) {
  if (task.is_completed) {
    return { text: "已完成", variant: "secondary" as const, overdue: false }
  }
  if (task.end_date < today) {
    const days = dayOffset(today, task.end_date)
    return {
      text: `已逾期 ${days} 天`,
      variant: "destructive" as const,
      overdue: true,
    }
  }
  if (task.start_date <= today && task.end_date >= today) {
    const left = dayOffset(task.end_date, today) + 1
    return {
      text: `进行中 · 剩 ${left} 天`,
      variant: "default" as const,
      overdue: false,
    }
  }
  const diff = dayOffset(task.start_date, today)
  if (diff === 1) {
    return { text: "明天开始", variant: "outline" as const, overdue: false }
  }
  if (diff === 2) {
    return { text: "后天开始", variant: "outline" as const, overdue: false }
  }
  return {
    text: `${diff} 天后开始`,
    variant: "outline" as const,
    overdue: false,
  }
}

function TaskBar({
  task,
  origin,
  color,
  onOpenEdit,
}: {
  task: StudyTaskPublic
  origin: string
  color: string
  onOpenEdit: () => void
}) {
  const start = dayOffset(task.start_date, origin)
  const span = Math.max(dayOffset(task.end_date, task.start_date) + 1, 1)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onOpenEdit}
          className={cn(
            "absolute top-2 h-8 min-w-7 rounded-md px-2 text-left shadow-xs transition-all hover:ring-2 hover:ring-primary/40 focus:outline-none",
            task.is_completed ? "opacity-45" : "opacity-95",
          )}
          style={{
            left: start * AGGREGATED_DAY_WIDTH + 2,
            width: Math.max(span * AGGREGATED_DAY_WIDTH - 4, 32),
            backgroundColor: color,
          }}
          aria-label={`${task.title}：${dateLabel(task.start_date)}—${dateLabel(task.end_date)}`}
        >
          <span
            className={cn(
              "line-clamp-1 text-[11px] font-medium text-white select-none drop-shadow-xs",
              task.is_completed && "line-through opacity-85",
            )}
          >
            {task.title}
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs space-y-1">
        <p className="font-medium">{task.title}</p>
        {task.description ? (
          <p className="text-xs text-muted-foreground">{task.description}</p>
        ) : null}
        <p className="text-xs">
          {dateLabel(task.start_date)} — {dateLabel(task.end_date)}
        </p>
        <p className="text-xs">每天预计 {task.estimated_minutes} 分钟</p>
        <p className="font-medium text-primary text-xs">
          {task.is_completed ? "✓ 已完成" : "⏳ 进行中"}
        </p>
        <p className="text-[11px] text-muted-foreground">点击快速编辑任务</p>
      </TooltipContent>
    </Tooltip>
  )
}

export function AggregatedGantt({ plans }: AggregatedGanttProps) {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const [activeTab, setActiveTab] = useState<"timeline" | "pipeline" | "table">(
    "timeline",
  )
  const [planFilter, setPlanFilter] = useState<string>("all")
  const [filterMode, setFilterMode] = useState<"all" | "active" | "completed">(
    "all",
  )
  const [pipelineSort, setPipelineSort] = useState<
    "time_asc" | "time_desc" | "diff_desc" | "diff_asc" | "duration"
  >("time_asc")

  // Rename Conversation Dialog
  const [renameTarget, setRenameTarget] = useState<{
    conversationId: string
    currentTitle: string
  } | null>(null)
  const [newTitle, setNewTitle] = useState("")

  // Edit Plan Name / Details Dialog
  const [editingPlan, setEditingPlan] = useState<{
    id: string
    title: string
    summary: string
    reminder_enabled: boolean
  } | null>(null)

  // Quick Rename Plan Dialog
  const [quickRenamePlan, setQuickRenamePlan] = useState<{
    id: string
    title: string
  } | null>(null)
  const [planNewName, setPlanNewName] = useState("")

  // Delete Plan Confirmation
  const [deletingPlan, setDeletingPlan] = useState<{
    id: string
    title: string
  } | null>(null)

  // AI Adjust Dialog
  const [aiAdjustOpen, setAiAdjustOpen] = useState(false)
  const [aiTargetPlanId, setAiTargetPlanId] = useState<string>(
    plans[0]?.id || "",
  )
  const [aiInstruction, setAiInstruction] = useState("")

  // Edit Task Dialog
  const [editingTask, setEditingTask] = useState<{
    planId: string
    task: StudyTaskPublic
  } | null>(null)
  const [taskForm, setTaskForm] = useState<{
    title: string
    description: string
    start_date: string
    end_date: string
    estimated_minutes: number
    is_completed: boolean
  }>({
    title: "",
    description: "",
    start_date: "",
    end_date: "",
    estimated_minutes: 45,
    is_completed: false,
  })

  // Add Task Dialog
  const [addingTaskPlanId, setAddingTaskPlanId] = useState<string | null>(null)
  const [newTaskForm, setNewTaskForm] = useState<{
    title: string
    description: string
    start_date: string
    end_date: string
    estimated_minutes: number
  }>({
    title: "",
    description: "",
    start_date: localDateString(),
    end_date: localDateString(),
    estimated_minutes: 45,
  })

  // Mutations
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
      showSuccessToast("对话已重命名")
      setRenameTarget(null)
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const updatePlanMutation = useMutation({
    mutationFn: ({
      planId,
      request,
    }: {
      planId: string
      request: StudyPlanUpdate
    }) => studyPlansApi.updatePlan(planId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["study-plans"] })
      void queryClient.invalidateQueries({ queryKey: ["study-plan"] })
      showSuccessToast("学习计划已更新")
      setEditingPlan(null)
      setQuickRenamePlan(null)
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const deletePlanMutation = useMutation({
    mutationFn: (planId: string) => studyPlansApi.deletePlan(planId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["study-plans"] })
      void queryClient.invalidateQueries({ queryKey: ["study-plan"] })
      showSuccessToast("学习计划已删除")
      setDeletingPlan(null)
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const updateTaskMutation = useMutation({
    mutationFn: ({
      planId,
      taskId,
      request,
    }: {
      planId: string
      taskId: string
      request: StudyTaskUpdate
    }) => studyPlansApi.updateTask(planId, taskId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["study-plans"] })
      void queryClient.invalidateQueries({ queryKey: ["study-plan"] })
      showSuccessToast("任务状态已更新")
      setEditingTask(null)
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const createTaskMutation = useMutation({
    mutationFn: ({
      planId,
      request,
    }: {
      planId: string
      request: StudyTaskCreate
    }) => studyPlansApi.createTask(planId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["study-plans"] })
      void queryClient.invalidateQueries({ queryKey: ["study-plan"] })
      showSuccessToast("已添加新任务")
      setAddingTaskPlanId(null)
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const deleteTaskMutation = useMutation({
    mutationFn: ({ planId, taskId }: { planId: string; taskId: string }) =>
      studyPlansApi.deleteTask(planId, taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["study-plans"] })
      void queryClient.invalidateQueries({ queryKey: ["study-plan"] })
      showSuccessToast("任务已删除")
      setEditingTask(null)
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  const aiAdjustMutation = useMutation({
    mutationFn: ({
      planId,
      instruction,
    }: {
      planId: string
      instruction: string
    }) =>
      studyPlansApi.aiAdjust(planId, {
        instruction,
        timezone:
          Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai",
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["study-plans"] })
      void queryClient.invalidateQueries({ queryKey: ["study-plan"] })
      showSuccessToast("AI 已成功重新优化排期与甘特图！")
      setAiAdjustOpen(false)
      setAiInstruction("")
    },
    onError: (error) => showErrorToast(extractErrorMessage(error)),
  })

  // Enriched flat task pipeline
  const enrichedTasks = useMemo(() => {
    const list: EnrichedTask[] = []
    for (const plan of plans) {
      if (planFilter !== "all" && plan.id !== planFilter) continue
      const color = colorForNotebook(plan.notebook_id)
      for (const task of plan.tasks) {
        list.push({
          ...task,
          planId: plan.id,
          planTitle: plan.title,
          planDifficulty: plan.difficulty,
          notebookId: plan.notebook_id,
          notebookTitle: plan.notebook_title,
          conversationId: plan.conversation_id,
          color,
        })
      }
    }
    return list
  }, [plans, planFilter])

  const completedTasksCount = useMemo(
    () => enrichedTasks.filter((t) => t.is_completed).length,
    [enrichedTasks],
  )
  const progressPercent = useMemo(
    () =>
      enrichedTasks.length > 0
        ? Math.round((completedTasksCount / enrichedTasks.length) * 100)
        : 0,
    [enrichedTasks.length, completedTasksCount],
  )

  // Sorted and filtered pipeline
  const sequencedTasks = useMemo(() => {
    let filtered = enrichedTasks
    if (filterMode === "active") {
      filtered = filtered.filter((t) => !t.is_completed)
    } else if (filterMode === "completed") {
      filtered = filtered.filter((t) => t.is_completed)
    }

    return [...filtered].sort((a, b) => {
      if (pipelineSort === "time_asc") {
        if (a.is_completed !== b.is_completed) return a.is_completed ? 1 : -1
        return (
          a.start_date.localeCompare(b.start_date) ||
          a.end_date.localeCompare(b.end_date)
        )
      }
      if (pipelineSort === "time_desc") {
        if (a.is_completed !== b.is_completed) return a.is_completed ? 1 : -1
        return b.start_date.localeCompare(a.start_date)
      }
      if (pipelineSort === "diff_desc") {
        const diffA = DIFFICULTY_WEIGHT[a.planDifficulty] || 2
        const diffB = DIFFICULTY_WEIGHT[b.planDifficulty] || 2
        return diffB - diffA || a.start_date.localeCompare(b.start_date)
      }
      if (pipelineSort === "diff_asc") {
        const diffA = DIFFICULTY_WEIGHT[a.planDifficulty] || 2
        const diffB = DIFFICULTY_WEIGHT[b.planDifficulty] || 2
        return diffA - diffB || a.start_date.localeCompare(b.start_date)
      }
      if (pipelineSort === "duration") {
        return b.estimated_minutes - a.estimated_minutes
      }
      return 0
    })
  }, [enrichedTasks, filterMode, pipelineSort])

  const filteredPlans = useMemo(() => {
    let list = plans
    if (planFilter !== "all") {
      list = list.filter((p) => p.id === planFilter)
    }
    if (filterMode === "all") return list
    return list.map((p) => ({
      ...p,
      tasks: p.tasks.filter((t) =>
        filterMode === "completed" ? t.is_completed : !t.is_completed,
      ),
    }))
  }, [plans, planFilter, filterMode])

  const activePlansForTimeline = useMemo(() => {
    if (planFilter === "all") return plans
    return plans.filter((p) => p.id === planFilter)
  }, [plans, planFilter])

  const { start, duration } = useMemo(
    () => timelineBounds(activePlansForTimeline),
    [activePlansForTimeline],
  )
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

  const openTaskEdit = (planId: string, task: StudyTaskPublic) => {
    setEditingTask({ planId, task })
    setTaskForm({
      title: task.title,
      description: task.description || "",
      start_date: task.start_date,
      end_date: task.end_date,
      estimated_minutes: task.estimated_minutes,
      is_completed: task.is_completed,
    })
  }

  const openPlanEdit = (plan: StudyPlanListItem) => {
    setEditingPlan({
      id: plan.id,
      title: plan.title,
      summary: plan.summary,
      reminder_enabled: plan.reminder_enabled,
    })
  }

  const openQuickRename = (plan: StudyPlanListItem) => {
    setQuickRenamePlan({ id: plan.id, title: plan.title })
    setPlanNewName(plan.title)
  }

  const openAddTask = (planId: string) => {
    const plan = plans.find((p) => p.id === planId)
    const startDate = plan?.start_date || localDateString()
    const endDate = plan?.end_date || startDate
    setAddingTaskPlanId(planId)
    setNewTaskForm({
      title: "",
      description: "",
      start_date: startDate,
      end_date: endDate,
      estimated_minutes: 45,
    })
  }

  const openAiAdjust = (planId?: string) => {
    setAiTargetPlanId(planId || plans[0]?.id || "")
    setAiInstruction("")
    setAiAdjustOpen(true)
  }

  return (
    <div className="space-y-4">
      {/* Top Header Toolbar & AI Action & Stats */}
      <div className="flex flex-col gap-3 rounded-2xl border bg-card p-4 shadow-card lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <CheckCircle2 className="size-4" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">总计划进度</p>
              <p className="text-sm font-semibold">
                {plans.length} 计划 · {completedTasksCount}/
                {enrichedTasks.length} 任务完成
              </p>
            </div>
          </div>
          <div className="h-6 w-px bg-border hidden sm:block" />
          <div className="flex items-center gap-2 min-w-32">
            <div className="h-2 flex-1 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-300 rounded-full"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
            <span className="text-xs font-semibold tabular-nums text-muted-foreground">
              {progressPercent}%
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Plan / Conversation Filter Select */}
          {plans.length > 1 ? (
            <Select value={planFilter} onValueChange={setPlanFilter}>
              <SelectTrigger
                className="h-8 max-w-[190px] sm:max-w-[240px] text-xs font-medium bg-background"
                aria-label="筛选计划与会话"
              >
                <SelectValue placeholder="筛选计划与会话">
                  <div className="flex items-center gap-1.5 truncate">
                    {planFilter === "all" ? (
                      <span>全部计划 ({plans.length})</span>
                    ) : (
                      <>
                        <span
                          className="size-2 rounded-full shrink-0"
                          style={{
                            backgroundColor: colorForNotebook(
                              plans.find((p) => p.id === planFilter)
                                ?.notebook_id || "",
                            ),
                          }}
                        />
                        <span className="truncate font-medium">
                          {plans.find((p) => p.id === planFilter)?.title ||
                            "指定计划"}
                        </span>
                      </>
                    )}
                  </div>
                </SelectValue>
              </SelectTrigger>
              <SelectContent className="max-h-72">
                <SelectItem value="all" className="text-xs">
                  全部计划与会话 ({plans.length})
                </SelectItem>
                {plans.map((p) => (
                  <SelectItem
                    key={p.id}
                    value={p.id}
                    className="text-xs cursor-pointer"
                  >
                    <div className="flex items-center gap-1.5 truncate">
                      <span
                        className="size-2 rounded-full shrink-0"
                        style={{
                          backgroundColor: colorForNotebook(p.notebook_id),
                        }}
                      />
                      <span className="truncate font-medium">{p.title}</span>
                      <span className="text-[10px] text-muted-foreground truncate">
                        ({p.conversation_title})
                      </span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}

          {/* AI Copilot Button */}
          <Button
            variant="default"
            size="sm"
            onClick={() => openAiAdjust()}
            className="h-8 gap-1.5 shadow-xs bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <Sparkles className="size-3.5 animate-pulse" />
            <span className="text-xs font-medium">AI 智能调整计划</span>
          </Button>

          {/* View Tab Switcher */}
          <Tabs
            value={activeTab}
            onValueChange={(val) => setActiveTab(val as typeof activeTab)}
          >
            <TabsList className="h-8 p-0.5">
              <TabsTrigger value="timeline" className="text-xs px-2.5 h-7">
                <Calendar className="size-3 mr-1" />
                时间轴视图
              </TabsTrigger>
              <TabsTrigger value="pipeline" className="text-xs px-2.5 h-7">
                <ListOrdered className="size-3 mr-1" />
                执行流水线
              </TabsTrigger>
              <TabsTrigger value="table" className="text-xs px-2.5 h-7">
                明细列表
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Status Filter */}
          <div className="flex items-center gap-1 border-l pl-2">
            <Filter className="size-3.5 text-muted-foreground mr-1 hidden sm:block" />
            <Button
              variant={filterMode === "all" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 text-xs px-2"
              onClick={() => setFilterMode("all")}
            >
              全部
            </Button>
            <Button
              variant={filterMode === "active" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 text-xs px-2"
              onClick={() => setFilterMode("active")}
            >
              待办
            </Button>
            <Button
              variant={filterMode === "completed" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 text-xs px-2"
              onClick={() => setFilterMode("completed")}
            >
              已完
            </Button>
          </div>
        </div>
      </div>

      {legendNotebooks.length > 1 && activeTab === "timeline" ? (
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

      {/* 1. TIMELINE GANTT VIEW */}
      {activeTab === "timeline" && (
        <div className="isolate max-w-full overflow-x-auto rounded-2xl border bg-card shadow-card">
          <div
            className="grid min-w-max"
            style={{ gridTemplateColumns: `16rem ${timelineWidth}px` }}
          >
            <div className="sticky left-0 z-10 border-b border-r bg-card/95 backdrop-blur-xs px-4 py-3 text-xs font-medium text-muted-foreground">
              学习计划 / 任务进度
            </div>
            <div className="relative flex border-b bg-card">
              {days.map((index) => {
                const current = new Date(
                  parseDate(start).getTime() + index * 86_400_000,
                )
                return (
                  <div
                    key={current.toISOString()}
                    className="shrink-0 border-r px-0.5 py-2.5 text-center text-[10px] tabular-nums text-muted-foreground"
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

            {filteredPlans.map((plan) => {
              const color = colorForNotebook(plan.notebook_id)
              return (
                <div key={plan.id} className="contents">
                  <div className="sticky left-0 z-10 flex flex-col justify-center gap-1.5 border-r border-b bg-card px-4 py-3">
                    <div className="flex items-center justify-between gap-1">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <button
                          type="button"
                          onClick={() => openPlanEdit(plan)}
                          className="truncate text-left text-xs font-semibold hover:text-primary transition-colors cursor-pointer"
                          title={`编辑计划：${plan.title}`}
                        >
                          {plan.title}
                        </button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-4 shrink-0 text-muted-foreground hover:text-foreground"
                          title="修改计划名称"
                          onClick={() => openQuickRename(plan)}
                        >
                          <Pencil className="size-2.5" />
                        </Button>
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-5 shrink-0 rounded text-muted-foreground hover:text-foreground"
                          >
                            <MoreHorizontal className="size-3" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => openAiAdjust(plan.id)}
                          >
                            <Sparkles className="size-3.5 mr-2 text-primary" />
                            AI 智能重排此计划
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => openQuickRename(plan)}
                          >
                            <Pencil className="size-3.5 mr-2" />
                            修改计划名称
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openPlanEdit(plan)}>
                            <Calendar className="size-3.5 mr-2" />
                            编辑计划详情
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => openAddTask(plan.id)}
                          >
                            <Plus className="size-3.5 mr-2" />
                            添加任务
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={() =>
                              setDeletingPlan({
                                id: plan.id,
                                title: plan.title,
                              })
                            }
                          >
                            <Trash2 className="size-3.5 mr-2" />
                            删除计划
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <Link
                        to="/notebooks/$notebookId"
                        params={{ notebookId: plan.notebook_id }}
                        className="truncate hover:text-foreground transition-colors"
                        title={`笔记本：${plan.notebook_title}`}
                      >
                        {plan.notebook_title}
                      </Link>
                      <span>·</span>
                      <Link
                        to="/notebooks/$notebookId"
                        params={{ notebookId: plan.notebook_id }}
                        search={{ conversation: plan.conversation_id }}
                        className="truncate hover:text-primary transition-colors"
                        title={`问答：${plan.conversation_title}`}
                      >
                        {plan.conversation_title}
                      </Link>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-4 shrink-0 rounded p-0 text-muted-foreground/70 hover:text-foreground"
                        title="重命名对话"
                        onClick={() =>
                          setRenameTarget({
                            conversationId: plan.conversation_id,
                            currentTitle: plan.conversation_title,
                          })
                        }
                      >
                        <Pencil className="size-2.5" />
                      </Button>
                    </div>
                  </div>
                  <div
                    className="relative h-14 border-b"
                    style={{
                      backgroundImage:
                        "linear-gradient(to right, hsl(var(--border)) 1px, transparent 1px)",
                      backgroundSize: `${AGGREGATED_DAY_WIDTH}px 100%`,
                    }}
                  >
                    {showToday ? (
                      <div
                        aria-hidden="true"
                        className="pointer-events-none absolute inset-y-0 z-[1] w-px bg-primary/40"
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
                        onOpenEdit={() => openTaskEdit(plan.id, task)}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 2. UPCOMING / SEQUENCED EXECUTION PIPELINE */}
      {activeTab === "pipeline" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3 px-1">
            <div className="flex items-center gap-2">
              <ListOrdered className="size-4 text-primary" />
              <h3 className="text-sm font-semibold">
                逐个完成清单 · 待办执行流水线（{sequencedTasks.length} 项）
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <ArrowUpDown className="size-3.5 text-muted-foreground" />
              <Select
                value={pipelineSort}
                onValueChange={(val) =>
                  setPipelineSort(val as typeof pipelineSort)
                }
              >
                <SelectTrigger className="h-8 text-xs w-40">
                  <SelectValue placeholder="排序方式" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="time_asc">时间优先（近期优先）</SelectItem>
                  <SelectItem value="time_desc">
                    时间倒序（远期优先）
                  </SelectItem>
                  <SelectItem value="diff_desc">
                    难度优先（高难度挑战）
                  </SelectItem>
                  <SelectItem value="diff_asc">
                    循序渐进（基础入门优先）
                  </SelectItem>
                  <SelectItem value="duration">
                    时长降序（长任务优先）
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {sequencedTasks.map((task, idx) => {
              const statusInfo = getTaskRelativeStatus(task, today)
              return (
                <div
                  key={task.id}
                  className={cn(
                    "relative flex flex-col justify-between gap-2.5 rounded-xl border bg-card p-4 shadow-card transition-all hover:border-primary/40",
                    task.is_completed && "opacity-60 bg-muted/20",
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2.5 min-w-0">
                      <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground mt-0.5">
                        {idx + 1}
                      </div>
                      <div className="min-w-0">
                        <button
                          type="button"
                          onClick={() => openTaskEdit(task.planId, task)}
                          className={cn(
                            "text-left font-medium text-sm transition-colors hover:text-primary cursor-pointer line-clamp-1",
                            task.is_completed &&
                              "line-through text-muted-foreground",
                          )}
                        >
                          {task.title}
                        </button>
                        <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                          {task.planTitle} · {task.notebookTitle}
                        </p>
                      </div>
                    </div>
                    <Badge
                      variant={statusInfo.variant}
                      className="text-[10px] shrink-0"
                    >
                      {statusInfo.overdue ? (
                        <AlertCircle className="size-3 mr-1" />
                      ) : null}
                      {statusInfo.text}
                    </Badge>
                  </div>

                  {task.description ? (
                    <p className="text-xs text-muted-foreground/90 bg-muted/30 p-2 rounded-lg line-clamp-2">
                      {task.description}
                    </p>
                  ) : null}

                  <div className="flex items-center justify-between gap-2 pt-1 border-t text-xs text-muted-foreground">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1 tabular-nums">
                        <Calendar className="size-3" />
                        {dateLabel(task.start_date)} —{" "}
                        {dateLabel(task.end_date)}
                      </span>
                      <span className="flex items-center gap-1 tabular-nums">
                        <Clock className="size-3" />
                        {task.estimated_minutes} 分/天
                      </span>
                      <Badge
                        variant="secondary"
                        className="text-[10px] font-normal"
                      >
                        {difficultyLabels[
                          task.planDifficulty as keyof typeof difficultyLabels
                        ] || "进阶"}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-2">
                      <label
                        htmlFor={`pipeline-check-${task.id}`}
                        className="inline-flex items-center gap-1.5 cursor-pointer select-none"
                      >
                        <Checkbox
                          id={`pipeline-check-${task.id}`}
                          checked={task.is_completed}
                          onCheckedChange={(checked) =>
                            updateTaskMutation.mutate({
                              planId: task.planId,
                              taskId: task.id,
                              request: { is_completed: checked === true },
                            })
                          }
                        />
                        <span className="text-xs">
                          {task.is_completed ? "已完成" : "完成"}
                        </span>
                      </label>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 3. TASK DETAILS TABLE */}
      {activeTab === "table" && (
        <div className="isolate max-w-full overflow-x-auto rounded-2xl border bg-card shadow-card">
          <table className="w-full min-w-[50rem] text-left text-sm">
            <caption className="sr-only">学习计划任务明细表</caption>
            <thead className="bg-muted/40 text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">所属计划</th>
                <th className="px-4 py-3 font-medium">任务阶段</th>
                <th className="px-4 py-3 font-medium">时间安排</th>
                <th className="px-4 py-3 font-medium">耗时</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredPlans.flatMap((plan) =>
                plan.tasks.map((task) => (
                  <tr
                    key={task.id}
                    className="border-t transition-colors hover:bg-muted/20"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Link
                          to="/notebooks/$notebookId"
                          params={{ notebookId: plan.notebook_id }}
                          search={{ conversation: plan.conversation_id }}
                          className="font-medium hover:text-primary transition-colors line-clamp-1"
                          title={plan.title}
                        >
                          {plan.title}
                        </Link>
                        <Badge
                          variant="secondary"
                          className="font-normal shrink-0"
                        >
                          {difficultyLabels[plan.difficulty]}
                        </Badge>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => openTaskEdit(plan.id, task)}
                        className={cn(
                          "text-left font-medium transition-colors hover:text-primary cursor-pointer line-clamp-1",
                          task.is_completed &&
                            "text-muted-foreground line-through opacity-75",
                        )}
                      >
                        {task.title}
                      </button>
                      {task.description ? (
                        <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                          {task.description}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-xs text-muted-foreground whitespace-nowrap">
                      {dateLabel(task.start_date)} — {dateLabel(task.end_date)}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-xs text-muted-foreground whitespace-nowrap">
                      {task.estimated_minutes} 分钟/天
                    </td>
                    <td className="px-4 py-3">
                      <label
                        htmlFor={`task-check-row-${task.id}`}
                        className="inline-flex cursor-pointer items-center gap-2"
                      >
                        <Checkbox
                          id={`task-check-row-${task.id}`}
                          checked={task.is_completed}
                          onCheckedChange={(checked) =>
                            updateTaskMutation.mutate({
                              planId: plan.id,
                              taskId: task.id,
                              request: { is_completed: checked === true },
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
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 rounded text-muted-foreground hover:text-foreground"
                          title="编辑任务"
                          onClick={() => openTaskEdit(plan.id, task)}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 rounded text-muted-foreground hover:text-destructive"
                          title="删除任务"
                          onClick={() =>
                            deleteTaskMutation.mutate({
                              planId: plan.id,
                              taskId: task.id,
                            })
                          }
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* AI Copilot Adjust Modal */}
      <Dialog open={aiAdjustOpen} onOpenChange={setAiAdjustOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bot className="size-5 text-primary" />
              AI 智能学习计划与甘特图调整
            </DialogTitle>
            <DialogDescription>
              向 AI
              提出调整意图（如排期顺延、周期缩短、更改计划名称、难度升降或添加重点实战），AI
              将自动重新编排并更新甘特图。
            </DialogDescription>
          </DialogHeader>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (
                !aiInstruction.trim() ||
                !aiTargetPlanId ||
                aiAdjustMutation.isPending
              )
                return
              aiAdjustMutation.mutate({
                planId: aiTargetPlanId,
                instruction: aiInstruction.trim(),
              })
            }}
            className="space-y-4"
          >
            {plans.length > 1 && (
              <div className="space-y-1.5">
                <Label htmlFor="ai-target-plan-select">目标学习计划</Label>
                <Select
                  value={aiTargetPlanId}
                  onValueChange={(val) => setAiTargetPlanId(val)}
                >
                  <SelectTrigger id="ai-target-plan-select" className="w-full">
                    <SelectValue placeholder="选择需要调整的计划" />
                  </SelectTrigger>
                  <SelectContent>
                    {plans.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.title} ({p.notebook_title})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                快捷调整模板：
              </Label>
              <div className="flex flex-wrap gap-1.5">
                {AI_PROMPT_PRESETS.map((preset) => (
                  <Button
                    key={preset.label}
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs px-2.5 rounded-full hover:border-primary"
                    onClick={() => setAiInstruction(preset.prompt)}
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="ai-instruction-input">您的调整要求与意图</Label>
              <textarea
                id="ai-instruction-input"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 min-h-[90px]"
                value={aiInstruction}
                onChange={(e) => setAiInstruction(e.target.value)}
                placeholder="例如：将计划名称改为《精通强化学习实战》，总周期延长至 3 周，增加强化学习算法复现任务，并把难度设为 advanced…"
                maxLength={2000}
                required
                autoFocus
              />
            </div>

            <DialogFooter className="gap-2 sm:gap-0 justify-between items-center">
              <DialogClose asChild>
                <Button type="button" variant="outline">
                  取消
                </Button>
              </DialogClose>
              <Button
                type="submit"
                disabled={
                  !aiInstruction.trim() ||
                  !aiTargetPlanId ||
                  aiAdjustMutation.isPending
                }
                className="gap-2"
              >
                <Sparkles className="size-4" />
                {aiAdjustMutation.isPending
                  ? "AI 智能调整中…"
                  : "让 AI 重新规划"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Quick Rename Plan Dialog */}
      <Dialog
        open={Boolean(quickRenamePlan)}
        onOpenChange={(open) => {
          if (!open) setQuickRenamePlan(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>修改学习计划名称</DialogTitle>
            <DialogDescription>
              设置此学习计划在甘特图与仪表板中的显示标题。
            </DialogDescription>
          </DialogHeader>
          {quickRenamePlan ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const trimmed = planNewName.trim()
                if (!trimmed || updatePlanMutation.isPending) return
                updatePlanMutation.mutate({
                  planId: quickRenamePlan.id,
                  request: { title: trimmed },
                })
              }}
              className="space-y-4"
            >
              <Input
                value={planNewName}
                onChange={(e) => setPlanNewName(e.target.value)}
                placeholder="输入计划名称"
                maxLength={100}
                autoFocus
                required
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
                    !planNewName.trim() ||
                    planNewName.trim() === quickRenamePlan.title ||
                    updatePlanMutation.isPending
                  }
                >
                  {updatePlanMutation.isPending ? "保存中…" : "保存"}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Full Edit Plan Dialog */}
      <Dialog
        open={Boolean(editingPlan)}
        onOpenChange={(open) => {
          if (!open) setEditingPlan(null)
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>编辑学习计划详情</DialogTitle>
            <DialogDescription>
              修改计划的展示标题与总结目标。
            </DialogDescription>
          </DialogHeader>
          {editingPlan ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const trimmed = editingPlan.title.trim()
                if (!trimmed || updatePlanMutation.isPending) return
                updatePlanMutation.mutate({
                  planId: editingPlan.id,
                  request: {
                    title: trimmed,
                    summary: editingPlan.summary.trim(),
                    reminder_enabled: editingPlan.reminder_enabled,
                  },
                })
              }}
              className="space-y-4"
            >
              <div className="space-y-1.5">
                <Label htmlFor="plan-full-title-input">计划标题</Label>
                <Input
                  id="plan-full-title-input"
                  value={editingPlan.title}
                  onChange={(e) =>
                    setEditingPlan({ ...editingPlan, title: e.target.value })
                  }
                  placeholder="计划名称"
                  maxLength={100}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plan-summary-input">计划目标与总结</Label>
                <textarea
                  id="plan-summary-input"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 min-h-[80px]"
                  value={editingPlan.summary}
                  onChange={(e) =>
                    setEditingPlan({ ...editingPlan, summary: e.target.value })
                  }
                  placeholder="学习目标说明"
                  maxLength={1000}
                />
              </div>
              <div className="flex items-center gap-2 pt-1">
                <Checkbox
                  id="plan-reminder-check"
                  checked={editingPlan.reminder_enabled}
                  onCheckedChange={(checked) =>
                    setEditingPlan({
                      ...editingPlan,
                      reminder_enabled: checked === true,
                    })
                  }
                />
                <Label
                  htmlFor="plan-reminder-check"
                  className="text-xs font-medium cursor-pointer"
                >
                  开启每日学习进度邮件提醒
                </Label>
              </div>
              <DialogFooter className="gap-2 sm:gap-0">
                <DialogClose asChild>
                  <Button type="button" variant="outline">
                    取消
                  </Button>
                </DialogClose>
                <Button type="submit" disabled={updatePlanMutation.isPending}>
                  {updatePlanMutation.isPending ? "保存中…" : "保存修改"}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Delete Plan Confirmation Dialog */}
      <Dialog
        open={Boolean(deletingPlan)}
        onOpenChange={(open) => {
          if (!open) setDeletingPlan(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>确认删除学习计划？</DialogTitle>
            <DialogDescription>
              将永久删除计划「{deletingPlan?.title}
              」及其关联的全部任务阶段，该操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0">
            <DialogClose asChild>
              <Button type="button" variant="outline">
                取消
              </Button>
            </DialogClose>
            <Button
              type="button"
              variant="destructive"
              disabled={deletePlanMutation.isPending}
              onClick={() => {
                if (deletingPlan) deletePlanMutation.mutate(deletingPlan.id)
              }}
            >
              {deletePlanMutation.isPending ? "删除中…" : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Task Dialog */}
      <Dialog
        open={Boolean(editingTask)}
        onOpenChange={(open) => {
          if (!open) setEditingTask(null)
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>编辑任务阶段</DialogTitle>
            <DialogDescription>
              调整任务内容、学习周期与完成状态。
            </DialogDescription>
          </DialogHeader>
          {editingTask ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const trimmed = taskForm.title.trim()
                if (!trimmed || updateTaskMutation.isPending) return
                updateTaskMutation.mutate({
                  planId: editingTask.planId,
                  taskId: editingTask.task.id,
                  request: {
                    title: trimmed,
                    description: taskForm.description.trim(),
                    start_date: taskForm.start_date,
                    end_date: taskForm.end_date,
                    estimated_minutes: taskForm.estimated_minutes,
                    is_completed: taskForm.is_completed,
                  },
                })
              }}
              className="space-y-4"
            >
              <div className="space-y-1.5">
                <Label htmlFor="edit-task-title">任务名称</Label>
                <Input
                  id="edit-task-title"
                  value={taskForm.title}
                  onChange={(e) =>
                    setTaskForm({ ...taskForm, title: e.target.value })
                  }
                  placeholder="任务名称"
                  maxLength={100}
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label
                    htmlFor="edit-task-start-date"
                    className="flex items-center gap-1"
                  >
                    <Calendar className="size-3" /> 开始日期
                  </Label>
                  <Input
                    id="edit-task-start-date"
                    type="date"
                    value={taskForm.start_date}
                    onChange={(e) =>
                      setTaskForm({ ...taskForm, start_date: e.target.value })
                    }
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label
                    htmlFor="edit-task-end-date"
                    className="flex items-center gap-1"
                  >
                    <Calendar className="size-3" /> 结束日期
                  </Label>
                  <Input
                    id="edit-task-end-date"
                    type="date"
                    value={taskForm.end_date}
                    onChange={(e) =>
                      setTaskForm({ ...taskForm, end_date: e.target.value })
                    }
                    required
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 items-center">
                <div className="space-y-1.5">
                  <Label
                    htmlFor="edit-task-duration"
                    className="flex items-center gap-1"
                  >
                    <Clock className="size-3" /> 每日预计时长（分钟）
                  </Label>
                  <Input
                    id="edit-task-duration"
                    type="number"
                    min={15}
                    max={480}
                    step={5}
                    value={taskForm.estimated_minutes}
                    onChange={(e) =>
                      setTaskForm({
                        ...taskForm,
                        estimated_minutes: Number(e.target.value),
                      })
                    }
                    required
                  />
                </div>
                <div className="flex items-center gap-2 pt-5">
                  <Checkbox
                    id="edit-task-completed"
                    checked={taskForm.is_completed}
                    onCheckedChange={(checked) =>
                      setTaskForm({
                        ...taskForm,
                        is_completed: checked === true,
                      })
                    }
                  />
                  <Label
                    htmlFor="edit-task-completed"
                    className="text-xs font-medium cursor-pointer"
                  >
                    标记为已完成
                  </Label>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-task-desc">任务详细描述与说明</Label>
                <textarea
                  id="edit-task-desc"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 min-h-[70px]"
                  value={taskForm.description}
                  onChange={(e) =>
                    setTaskForm({ ...taskForm, description: e.target.value })
                  }
                  placeholder="任务要点或学习笔记…"
                  maxLength={500}
                />
              </div>
              <DialogFooter className="gap-2 sm:gap-0 justify-between items-center">
                <Button
                  type="button"
                  variant="ghost"
                  className="text-destructive hover:bg-destructive/10"
                  onClick={() =>
                    deleteTaskMutation.mutate({
                      planId: editingTask.planId,
                      taskId: editingTask.task.id,
                    })
                  }
                >
                  <Trash2 className="size-3.5 mr-1" />
                  删除任务
                </Button>
                <div className="flex gap-2">
                  <DialogClose asChild>
                    <Button type="button" variant="outline">
                      取消
                    </Button>
                  </DialogClose>
                  <Button type="submit" disabled={updateTaskMutation.isPending}>
                    {updateTaskMutation.isPending ? "保存中…" : "保存任务"}
                  </Button>
                </div>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Add Task Dialog */}
      <Dialog
        open={Boolean(addingTaskPlanId)}
        onOpenChange={(open) => {
          if (!open) setAddingTaskPlanId(null)
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>添加新任务阶段</DialogTitle>
            <DialogDescription>
              为此计划新增一个自定义学习阶段或任务目标。
            </DialogDescription>
          </DialogHeader>
          {addingTaskPlanId ? (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                const trimmed = newTaskForm.title.trim()
                if (!trimmed || createTaskMutation.isPending) return
                createTaskMutation.mutate({
                  planId: addingTaskPlanId,
                  request: {
                    title: trimmed,
                    description: newTaskForm.description.trim(),
                    start_date: newTaskForm.start_date,
                    end_date: newTaskForm.end_date,
                    estimated_minutes: newTaskForm.estimated_minutes,
                  },
                })
              }}
              className="space-y-4"
            >
              <div className="space-y-1.5">
                <Label htmlFor="new-task-title">任务名称</Label>
                <Input
                  id="new-task-title"
                  value={newTaskForm.title}
                  onChange={(e) =>
                    setNewTaskForm({ ...newTaskForm, title: e.target.value })
                  }
                  placeholder="例如：精读第三章核心定理与例题"
                  maxLength={100}
                  required
                  autoFocus
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label
                    htmlFor="new-task-start-date"
                    className="flex items-center gap-1"
                  >
                    <Calendar className="size-3" /> 开始日期
                  </Label>
                  <Input
                    id="new-task-start-date"
                    type="date"
                    value={newTaskForm.start_date}
                    onChange={(e) =>
                      setNewTaskForm({
                        ...newTaskForm,
                        start_date: e.target.value,
                      })
                    }
                    required
                  />
                </div>
                <div className="space-y-1.5">
                  <Label
                    htmlFor="new-task-end-date"
                    className="flex items-center gap-1"
                  >
                    <Calendar className="size-3" /> 结束日期
                  </Label>
                  <Input
                    id="new-task-end-date"
                    type="date"
                    value={newTaskForm.end_date}
                    onChange={(e) =>
                      setNewTaskForm({
                        ...newTaskForm,
                        end_date: e.target.value,
                      })
                    }
                    required
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label
                  htmlFor="new-task-duration"
                  className="flex items-center gap-1"
                >
                  <Clock className="size-3" /> 每日预计时长（分钟）
                </Label>
                <Input
                  id="new-task-duration"
                  type="number"
                  min={15}
                  max={480}
                  step={5}
                  value={newTaskForm.estimated_minutes}
                  onChange={(e) =>
                    setNewTaskForm({
                      ...newTaskForm,
                      estimated_minutes: Number(e.target.value),
                    })
                  }
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="new-task-desc">任务详细说明（选填）</Label>
                <textarea
                  id="new-task-desc"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 min-h-[70px]"
                  value={newTaskForm.description}
                  onChange={(e) =>
                    setNewTaskForm({
                      ...newTaskForm,
                      description: e.target.value,
                    })
                  }
                  placeholder="任务要点或学习笔记…"
                  maxLength={500}
                />
              </div>
              <DialogFooter className="gap-2 sm:gap-0">
                <DialogClose asChild>
                  <Button type="button" variant="outline">
                    取消
                  </Button>
                </DialogClose>
                <Button type="submit" disabled={createTaskMutation.isPending}>
                  {createTaskMutation.isPending ? "添加中…" : "确认添加"}
                </Button>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Rename Conversation Dialog */}
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
