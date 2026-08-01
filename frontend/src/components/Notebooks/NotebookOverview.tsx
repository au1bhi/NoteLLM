import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RefreshCw, Sparkles } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { notebooksApi } from "@/services/notebooks"
import { extractErrorMessage } from "@/utils"

interface NotebookOverviewProps {
  notebookId: string
  hasReadySources: boolean
}

export function NotebookOverview({
  notebookId,
  hasReadySources,
}: NotebookOverviewProps) {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const { data, isLoading, error } = useQuery({
    enabled: hasReadySources,
    retry: false,
    queryKey: ["notebooks", notebookId, "overview"],
    queryFn: () => notebooksApi.getOverview(notebookId),
  })

  const regenerate = useMutation({
    mutationFn: () => notebooksApi.regenerateOverview(notebookId),
    onError: (err: Error) => showErrorToast(err.message),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "overview"],
      })
    },
  })

  if (!hasReadySources) return null

  return (
    <section className="rounded-xl border bg-card p-5 shadow-soft">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold tracking-tight">
          <span className="inline-flex size-6 items-center justify-center rounded-md bg-brand-gradient-soft text-primary">
            <Sparkles className="size-3.5" />
          </span>
          笔记本概览
        </h2>
        <Button
          variant="ghost"
          size="sm"
          disabled={regenerate.isPending}
          onClick={() => regenerate.mutate()}
        >
          <RefreshCw
            className={cn("size-3.5", regenerate.isPending && "animate-spin")}
          />
          重新生成
        </Button>
      </div>

      {isLoading ? (
        <div className="mt-4 space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ) : null}
      {error ? (
        <p className="mt-4 text-sm text-destructive">
          {extractErrorMessage(error)}
        </p>
      ) : null}
      {data?.summary ? (
        <>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
            {data.summary}
          </p>
          {data.topics.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {data.topics.map((topic) => (
                <span
                  key={topic}
                  className="rounded-full border bg-muted/40 px-3 py-1 text-xs font-medium text-muted-foreground"
                >
                  {topic}
                </span>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  )
}
