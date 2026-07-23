import { useQuery } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { BookOpen } from "lucide-react"

import { AddNotebook } from "@/components/Notebooks/AddNotebook"
import { notebooksApi } from "@/services/notebooks"

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
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Notebooks</h1>
          <p className="text-muted-foreground">
            Organize sources and grounded conversations.
          </p>
        </div>
        <AddNotebook />
      </div>
      {isLoading ? (
        <p className="text-muted-foreground">Loading notebooks…</p>
      ) : null}
      {error ? <p className="text-destructive">{error.message}</p> : null}
      {data?.data.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.data.map((notebook) => (
            <Link
              key={notebook.id}
              to="/notebooks/$notebookId"
              params={{ notebookId: notebook.id }}
              className="rounded-lg border p-5 transition-colors hover:bg-muted"
            >
              <BookOpen className="mb-4 size-5 text-primary" />
              <h2 className="font-semibold">{notebook.title}</h2>
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                {notebook.description || "No description yet"}
              </p>
            </Link>
          ))}
        </div>
      ) : null}
      {!isLoading && !error && data?.data.length === 0 ? (
        <div className="rounded-lg border border-dashed px-6 py-16 text-center">
          <BookOpen className="mx-auto mb-4 size-8 text-muted-foreground" />
          <h2 className="text-lg font-semibold">Create your first notebook</h2>
          <p className="mt-1 text-muted-foreground">
            Add a notebook to begin organizing your learning sources.
          </p>
          <AddNotebook />
        </div>
      ) : null}
    </div>
  )
}
