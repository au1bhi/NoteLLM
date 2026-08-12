import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { BookOpen } from "lucide-react"

import { type Notebook, notebooksApi } from "@/services/notebooks"
import { timeAgo } from "@/utils"
import { DeleteNotebook } from "./DeleteNotebook"
import { EditNotebook } from "./EditNotebook"
import { PinButton } from "./PinButton"

interface NotebookCardProps {
  notebook: Notebook
}

export function NotebookCard({ notebook }: NotebookCardProps) {
  const queryClient = useQueryClient()

  const pinMutation = useMutation({
    mutationFn: (isPinned: boolean) =>
      notebooksApi.update(notebook.id, { is_pinned: isPinned }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["notebooks"] })
      queryClient.invalidateQueries({ queryKey: ["notebooks", notebook.id] })
    },
  })

  return (
    <div className="group relative isolate">
      <div className="absolute right-3 top-3 z-10 flex translate-x-1 items-center gap-0.5 opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100 group-hover:pointer-events-auto focus-within:pointer-events-auto max-sm:pointer-events-auto max-sm:translate-x-0 max-sm:opacity-100 pointer-events-none">
        <PinButton
          pinned={Boolean(notebook.is_pinned)}
          disabled={pinMutation.isPending}
          className="size-8 rounded-lg text-muted-foreground hover:text-foreground"
          onToggle={() => pinMutation.mutate(!notebook.is_pinned)}
        />
        <EditNotebook
          notebook={notebook}
          triggerClassName="size-8 rounded-lg text-muted-foreground hover:text-foreground"
        />
        <DeleteNotebook
          notebook={notebook}
          triggerClassName="size-8 rounded-lg text-muted-foreground hover:text-destructive"
        />
      </div>
      <Link
        to="/notebooks/$notebookId"
        params={{ notebookId: notebook.id }}
        search={{}}
        className="flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-card"
      >
        <span className="inline-flex size-10 items-center justify-center rounded-lg bg-brand-gradient-soft text-primary transition-all duration-300 group-hover:bg-brand-gradient group-hover:text-white">
          <BookOpen className="size-5" />
        </span>
        <div>
          <h2 className="line-clamp-1 font-semibold tracking-tight">
            {notebook.title}
          </h2>
          <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
            {notebook.description || "暂无描述"}
          </p>
        </div>
        <p className="mt-auto pt-1 text-xs text-muted-foreground">
          更新于 {timeAgo(notebook.updated_at)}
        </p>
      </Link>
    </div>
  )
}
