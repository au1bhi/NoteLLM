import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { BookOpen } from "lucide-react"

import { AddNotebook } from "@/components/Notebooks/AddNotebook"
import { NotebookCard } from "@/components/Notebooks/NotebookCard"
import { Skeleton } from "@/components/ui/skeleton"
import { notebooksApi } from "@/services/notebooks"
import { sortPinnedFirst } from "@/utils"

export const Route = createFileRoute("/_layout/notebooks/")({
  component: Notebooks,
  head: () => ({ meta: [{ title: "Notebooks - NoteLLM" }] }),
})

function Notebooks() {
  const { data, error, isLoading } = useQuery({
    queryFn: notebooksApi.list,
    queryKey: ["notebooks"],
  })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">
            笔记本
          </h1>
          <p className="mt-1 text-muted-foreground">
            组织资料并开启带引用的问答会话。
          </p>
        </div>
        <AddNotebook />
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      ) : null}
      {error ? (
        <p className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {error.message}
        </p>
      ) : null}

      {!isLoading && !error && data?.data.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sortPinnedFirst(data.data).map((notebook) => (
            <NotebookCard key={notebook.id} notebook={notebook} />
          ))}
        </div>
      ) : null}

      {!isLoading && !error && data?.data.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed px-6 py-16 text-center">
          <span className="inline-flex size-14 items-center justify-center rounded-2xl bg-brand-gradient-soft text-primary">
            <BookOpen className="size-7" />
          </span>
          <div>
            <h2 className="text-lg font-semibold tracking-tight">
              创建你的第一个笔记本
            </h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              上传讲义或研究资料，即可开始只基于这些内容的问答。
            </p>
          </div>
          <AddNotebook />
        </div>
      ) : null}
    </div>
  )
}
