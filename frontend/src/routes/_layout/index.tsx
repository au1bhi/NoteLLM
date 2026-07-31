import { useQueries, useQuery } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  FileText,
  MessagesSquare,
  Quote,
  Sparkles,
  Upload,
} from "lucide-react"
import type { ComponentType } from "react"
import { AddNotebook } from "@/components/Notebooks/AddNotebook"
import { NotebookCard } from "@/components/Notebooks/NotebookCard"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import useAuth from "@/hooks/useAuth"
import { cn } from "@/lib/utils"
import { conversationsApi } from "@/services/conversations"
import { notebooksApi } from "@/services/notebooks"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [{ title: "Dashboard - NoteLLM" }],
  }),
})

const STEPS = [
  {
    icon: Upload,
    title: "上传资料",
    description:
      "把讲义、研究资料或笔记放入笔记本，支持 PDF、TXT 与 Markdown，自动解析并向量化。",
  },
  {
    icon: MessagesSquare,
    title: "在资料内提问",
    description:
      "问答只限定在当前笔记本的资料范围内，不依赖模型既有的知识猜测。",
  },
  {
    icon: Quote,
    title: "获得带引用的答案",
    description: "每个答案都附上来源、页码与原文摘录，可逐条回溯验证。",
  },
]

function StatCard({
  label,
  value,
  icon: Icon,
  tone,
  loading,
}: {
  label: string
  value: number
  icon: ComponentType<{ className?: string }>
  tone: string
  loading: boolean
}) {
  return (
    <div className="flex items-center gap-4 rounded-xl border bg-card p-5 shadow-soft">
      <span
        className={cn(
          "inline-flex size-11 shrink-0 items-center justify-center rounded-xl",
          tone,
        )}
      >
        <Icon className="size-5" />
      </span>
      <div className="min-w-0">
        {loading ? (
          <Skeleton className="h-7 w-12" />
        ) : (
          <p className="text-2xl font-semibold tracking-tight tabular-nums">
            {value}
          </p>
        )}
        <p className="truncate text-sm text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}

function Dashboard() {
  const { user: currentUser } = useAuth()
  const notebooks = useQuery({
    queryFn: notebooksApi.list,
    queryKey: ["notebooks"],
  })
  const ids = notebooks.data?.data.map((notebook) => notebook.id) ?? []

  const sources = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["notebooks", id, "sources"],
      queryFn: () => notebooksApi.listSources(id),
    })),
  })
  const conversations = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["notebooks", id, "conversations"],
      queryFn: () => conversationsApi.list(id),
    })),
  })

  const loading =
    notebooks.isLoading || sources.some((query) => query.isLoading)

  const sourceCount = sources.reduce(
    (sum, query) => sum + (query.data?.data.length ?? 0),
    0,
  )
  const readyCount = sources.reduce(
    (sum, query) =>
      sum +
      (query.data?.data.filter((source) => source.status === "ready").length ??
        0),
    0,
  )
  const conversationCount = conversations.reduce(
    (sum, query) => sum + (query.data?.data.length ?? 0),
    0,
  )

  const stats = [
    {
      label: "笔记本",
      value: notebooks.data?.data.length ?? 0,
      icon: BookOpen,
      tone: "bg-primary/10 text-primary",
    },
    {
      label: "资料来源",
      value: sourceCount,
      icon: FileText,
      tone: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
    },
    {
      label: "已就绪来源",
      value: readyCount,
      icon: CheckCircle2,
      tone: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    },
    {
      label: "问答会话",
      value: conversationCount,
      icon: MessagesSquare,
      tone: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    },
  ]

  const name = currentUser?.full_name || currentUser?.email || "同学"

  return (
    <div className="flex flex-col gap-6">
      <section className="relative overflow-hidden rounded-2xl bg-brand-gradient p-6 text-white shadow-card md:p-10">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-16 -top-24 size-72 rounded-full bg-white/10 blur-2xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-28 right-32 size-64 rounded-full bg-white/10 blur-3xl"
        />
        <div className="relative z-10 max-w-2xl">
          <p className="inline-flex items-center gap-1.5 text-sm font-medium text-white/80">
            <Sparkles className="size-4" />
            Welcome back
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">
            你好，{name}
          </h1>
          <p className="mt-3 max-w-xl text-white/85">
            把课程讲义、研究资料和笔记放进笔记本，在限定资料范围内提问，获得带可追溯引用的答案。
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <AddNotebook triggerClassName="bg-white text-primary shadow-soft hover:bg-white/90" />
            <Button
              variant="ghost"
              asChild
              className="text-white hover:bg-white/15 hover:text-white"
            >
              <Link to="/notebooks">
                浏览笔记本
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} loading={loading} />
        ))}
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold tracking-tight">最近笔记本</h2>
            <Link
              to="/notebooks"
              className="text-sm font-medium text-primary hover:underline"
            >
              查看全部
            </Link>
          </div>
          {notebooks.isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Skeleton className="h-36 rounded-xl" />
              <Skeleton className="h-36 rounded-xl" />
            </div>
          ) : null}
          {notebooks.data?.data.length ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {notebooks.data.data.slice(0, 6).map((notebook) => (
                <NotebookCard key={notebook.id} notebook={notebook} />
              ))}
            </div>
          ) : null}
          {!notebooks.isLoading && notebooks.data?.data.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed px-6 py-14 text-center">
              <span className="inline-flex size-12 items-center justify-center rounded-xl bg-brand-gradient-soft text-primary">
                <BookOpen className="size-6" />
              </span>
              <div>
                <h3 className="font-semibold">创建你的第一个笔记本</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  上传资料后即可开始有依据的问答。
                </p>
              </div>
              <AddNotebook />
            </div>
          ) : null}
        </section>

        <section className="h-fit rounded-xl border bg-card p-6 shadow-soft lg:sticky lg:top-24">
          <h2 className="text-lg font-semibold tracking-tight">如何使用</h2>
          <ol className="mt-5 space-y-5">
            {STEPS.map((step, index) => (
              <li key={step.title} className="flex gap-4">
                <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg bg-brand-gradient text-sm font-semibold text-white shadow-soft">
                  {index + 1}
                </span>
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <step.icon className="size-4 text-primary" />
                    {step.title}
                  </h3>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                    {step.description}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  )
}
