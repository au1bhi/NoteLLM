import { Link } from "@tanstack/react-router"
import { BookOpen } from "lucide-react"

import type { Notebook } from "@/services/notebooks"
import { timeAgo } from "@/utils"
import { DeleteNotebook } from "./DeleteNotebook"
import { EditNotebook } from "./EditNotebook"

interface NotebookCardProps {
  notebook: Notebook
}

export function NotebookCard({ notebook }: NotebookCardProps) {
  return (
    <div className="group relative isolate">
      <div className="absolute right-3 top-3 z-10 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100 max-sm:opacity-100">
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
        className="flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-card"
      >
        <span className="inline-flex size-10 items-center justify-center rounded-lg bg-brand-gradient-soft text-primary transition-colors group-hover:text-foreground">
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
