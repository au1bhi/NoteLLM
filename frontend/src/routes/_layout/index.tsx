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
import { InkMountains } from "@/components/Common/InkMountains"
import { OnboardingChecklist } from "@/components/Common/OnboardingChecklist"
import { AddNotebook } from "@/components/Notebooks/AddNotebook"
import { NotebookCard } from "@/components/Notebooks/NotebookCard"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import useAuth from "@/hooks/useAuth"
import { cn } from "@/lib/utils"
import { conversationsApi } from "@/services/conversations"
import { notebooksApi } from "@/services/notebooks"
import { sortPinnedFirst } from "@/utils"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [{ title: "首页 - NoteLLM" }],
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
    title: "选择回答模式再提问",
    description:
      "默认「仅依据资料」。也可改成结合已有知识，或完全不检索的自由问答。",
  },
  {
    icon: Quote,
    title: "核对引用或看到弃权",
    description:
      "「仅依据资料」时，有效引用会挂来源、页码与摘录；无证据则固定「资料不足」。",
  },
  {
    icon: Sparkles,
    title: "生成学习甘特图",
    description:
      "在会话里点「学习计划」，把一次问答安排成 3—60 天任务；侧边栏甘特图再把全部计划画在同一条时间轴上。",
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
    <div className="flex items-center gap-4 rounded-xl border bg-card p-5 shadow-soft transition-shadow hover:shadow-card">
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

  const sourcesByNotebook = new Map(
    ids.map((id, index) => [id, sources[index]?.data?.data ?? []]),
  )
  const firstNotebookId =
    notebooks.data?.data.find((notebook) =>
      (sourcesByNotebook.get(notebook.id) ?? []).some(
        (source) => source.status === "ready",
      ),
    )?.id ?? notebooks.data?.data[0]?.id

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
      tone: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
    },
    {
      label: "已就绪来源",
      value: readyCount,
      icon: CheckCircle2,
      tone: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    },
    {
      label: "问答会话",
      value: conversationCount,
      icon: MessagesSquare,
      tone: "bg-rose-500/10 text-rose-700 dark:text-rose-400",
    },
  ]

  const name = currentUser?.full_name || currentUser?.email || "同学"

  return (
    <div className="flex flex-col gap-6">
      <section className="relative isolate overflow-hidden rounded-2xl border bg-card p-6 shadow-card dark:bg-brand-gradient md:p-10">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-paper-grain opacity-40"
        />
        <InkMountains
          tone="paper"
          className="pointer-events-none absolute inset-x-0 bottom-0 h-3/5 w-full opacity-90 dark:hidden"
        />
        <InkMountains
          tone="ink"
          className="pointer-events-none absolute inset-x-0 bottom-0 hidden h-3/5 w-full opacity-70 dark:block"
        />
        <div className="relative z-10 max-w-2xl animate-rise">
          <p className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-sm font-medium text-primary backdrop-blur-sm dark:bg-white/10 dark:text-white">
            <Sparkles className="size-4" />
            欢迎回来
          </p>
          <h1 className="font-display mt-2 text-3xl font-semibold tracking-tight md:text-4xl">
            你好，{name}
          </h1>
          <p className="mt-3 max-w-xl text-muted-foreground dark:text-white/85">
            把课程讲义、研究资料和笔记放进笔记本。默认「仅依据资料」提问；无证据时固定弃权，而不是补造结论。
          </p>
          <div className="mt-7 flex flex-wrap items-center gap-3">
            <AddNotebook triggerClassName="bg-primary text-primary-foreground shadow-lifted transition-transform duration-200 hover:-translate-y-0.5 dark:bg-white dark:text-primary" />
            <Button
              variant="ghost"
              asChild
              className="text-foreground hover:bg-accent hover:text-accent-foreground dark:text-white dark:hover:bg-white/15 dark:hover:text-white"
            >
              <Link to="/notebooks">
                浏览笔记本
                <ArrowRight className="size-4" />
              </Link>
            </Button>
          </div>
        </div>
      </section>

      <OnboardingChecklist
        notebooksCount={notebooks.data?.data.length ?? 0}
        readySourcesCount={readyCount}
        conversationsCount={conversationCount}
        firstNotebookId={firstNotebookId}
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <StatCard key={stat.label} {...stat} loading={loading} />
        ))}
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold tracking-tight">
              最近笔记本
            </h2>
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
              {sortPinnedFirst(notebooks.data.data)
                .slice(0, 6)
                .map((notebook) => (
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
          <h2 className="font-display text-lg font-semibold tracking-tight">
            如何使用
          </h2>
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
