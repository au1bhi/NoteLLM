import { useMutation } from "@tanstack/react-query"
import {
  File,
  FileText,
  Loader2,
  RotateCcw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react"
import { type ChangeEvent, useRef, useState } from "react"

import type { RetrievedChunkPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { notebooksApi, type Source } from "@/services/notebooks"

interface SourcesPanelProps {
  notebookId: string
  sources?: Source[]
  selectedSourceIds: Set<string>
  isLoading: boolean
  isError: boolean
  errorMessage?: string
  isUploading: boolean
  isDeleting: boolean
  isRetrying: boolean
  className?: string
  onUploadFile: (file: File) => void
  onRetry: (sourceId: string) => void
  onDelete: (sourceId: string) => void
  onToggleSource: (sourceId: string) => void
  onSelectAll: () => void
}

function fileTone(mediaType: string) {
  if (mediaType.includes("pdf")) {
    return {
      Icon: FileText,
      tone: "bg-rose-500/10 text-rose-600 dark:text-rose-400",
    }
  }
  if (mediaType.includes("markdown")) {
    return {
      Icon: FileText,
      tone: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
    }
  }
  if (mediaType.includes("text")) {
    return { Icon: FileText, tone: "bg-primary/10 text-primary" }
  }
  return { Icon: File, tone: "bg-muted text-muted-foreground" }
}

function sourceMeta(source: Source): string {
  if (source.status === "ready") {
    const parts = []
    if (source.page_count) parts.push(`${source.page_count} 页`)
    if (source.char_count)
      parts.push(`${source.char_count.toLocaleString()} 字符`)
    return parts.length ? parts.join(" · ") : "已就绪"
  }
  if (source.status === "processing") return "正在解析并向量化…"
  return source.error_message || "处理失败"
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ready") {
    return (
      <Badge className="border-emerald-500/25 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
        已就绪
      </Badge>
    )
  }
  if (status === "processing") {
    return (
      <Badge className="border-amber-500/25 bg-amber-500/10 text-amber-600 dark:text-amber-400">
        <Loader2 className="animate-spin" />
        处理中
      </Badge>
    )
  }
  return (
    <Badge className="border-destructive/25 bg-destructive/10 text-destructive">
      失败
    </Badge>
  )
}

function SearchResults({
  results,
  isPending,
}: {
  results?: RetrievedChunkPublic[]
  isPending: boolean
}) {
  if (isPending) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 rounded-lg" />
        <Skeleton className="h-20 rounded-lg" />
      </div>
    )
  }
  if (!results?.length) {
    return (
      <p className="rounded-lg border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
        没有找到匹配的内容
      </p>
    )
  }
  return (
    <ul className="space-y-2">
      {results.map((result) => (
        <li key={result.id} className="rounded-lg border bg-background p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-xs font-medium">
              {result.source_display_name}
              {result.page_number != null ? ` · p. ${result.page_number}` : ""}
            </p>
            <span className="shrink-0 text-xs font-semibold text-primary">
              {Math.round(result.score * 100)}%
            </span>
          </div>
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-brand-gradient"
              style={{
                width: `${Math.max(4, Math.round(result.score * 100))}%`,
              }}
            />
          </div>
          <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
            {result.content}
          </p>
        </li>
      ))}
    </ul>
  )
}

export function SourcesPanel({
  notebookId,
  sources,
  selectedSourceIds,
  isLoading,
  isError,
  errorMessage,
  isUploading,
  isDeleting,
  isRetrying,
  className,
  onUploadFile,
  onRetry,
  onDelete,
  onToggleSource,
  onSelectAll,
}: SourcesPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { showErrorToast } = useCustomToast()
  const [searchQuery, setSearchQuery] = useState("")
  const [searched, setSearched] = useState(false)

  const searchMutation = useMutation({
    mutationFn: (query: string) => notebooksApi.search(notebookId, query),
    onError: (error: Error) => showErrorToast(error.message),
  })

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const [file] = Array.from(event.target.files ?? [])
    if (file) onUploadFile(file)
    event.target.value = ""
  }

  const submitSearch = () => {
    const query = searchQuery.trim()
    if (!query || searchMutation.isPending) return
    setSearched(true)
    searchMutation.mutate(query)
  }

  const clearSearch = () => {
    setSearched(false)
    setSearchQuery("")
    searchMutation.reset()
  }

  const readyCount =
    sources?.filter((source) => source.status === "ready").length ?? 0

  return (
    <section
      className={cn(
        "overflow-hidden rounded-xl border bg-card shadow-soft",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-3 border-b px-4 py-3.5">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold tracking-tight">资料</h2>
          {sources?.length ? (
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {readyCount}/{sources.length} 就绪
            </span>
          ) : null}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
          className="hidden"
          onChange={onFileChange}
        />
        <Button
          size="sm"
          disabled={isUploading}
          onClick={() => fileInputRef.current?.click()}
        >
          {isUploading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Upload className="size-4" />
          )}
          {isUploading ? "处理中" : "上传"}
        </Button>
      </header>

      <div className="border-b px-4 py-2">
        <div className="flex items-center gap-2">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <input
            value={searchQuery}
            placeholder="在资料中检索…"
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submitSearch()
            }}
            className="h-8 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {searched ? (
            <button
              type="button"
              aria-label="清除检索"
              onClick={clearSearch}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          ) : (
            <button
              type="button"
              aria-label="检索"
              onClick={submitSearch}
              disabled={searchMutation.isPending || !searchQuery.trim()}
              className="text-primary disabled:opacity-40"
            >
              {searchMutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}
            </button>
          )}
        </div>
      </div>

      <div className="p-4">
        {searched ? (
          <SearchResults
            results={searchMutation.data?.data}
            isPending={searchMutation.isPending}
          />
        ) : (
          <>
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-16 rounded-lg" />
                <Skeleton className="h-16 rounded-lg" />
              </div>
            ) : null}
            {isError ? (
              <p className="text-sm text-destructive">{errorMessage}</p>
            ) : null}
            {sources?.length ? (
              <>
                {readyCount > 0 ? (
                  <div className="mb-2 flex items-center justify-between gap-2 px-1">
                    <button
                      type="button"
                      onClick={onSelectAll}
                      className={cn(
                        "text-xs font-medium transition-colors",
                        selectedSourceIds.size === 0
                          ? "text-primary"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                    >
                      全部资料
                    </button>
                    <span className="text-xs text-muted-foreground">
                      {selectedSourceIds.size === 0
                        ? "使用全部资料"
                        : `已选 ${selectedSourceIds.size} 份`}
                    </span>
                  </div>
                ) : null}
                <ul className="space-y-2">
                  {sources.map((source) => {
                    const { Icon, tone } = fileTone(source.media_type)
                    return (
                      <li
                        key={source.id}
                        className="group flex items-center gap-3 rounded-lg border bg-background p-3 transition-colors hover:bg-muted/40"
                      >
                        {source.status === "ready" ? (
                          <Checkbox
                            checked={
                              selectedSourceIds.size === 0 ||
                              selectedSourceIds.has(source.id)
                            }
                            onCheckedChange={() => onToggleSource(source.id)}
                            aria-label={`选择 ${source.display_name}`}
                            className="shrink-0"
                          />
                        ) : null}
                        <span
                          className={cn(
                            "inline-flex size-9 shrink-0 items-center justify-center rounded-lg",
                            tone,
                          )}
                        >
                          <Icon className="size-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">
                            {source.display_name}
                          </p>
                          <div className="mt-1 flex items-center gap-2">
                            <StatusBadge status={source.status} />
                            <p className="truncate text-xs text-muted-foreground">
                              {sourceMeta(source)}
                            </p>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-0.5 opacity-100 transition-opacity group-hover:opacity-100 focus-within:opacity-100 max-lg:opacity-100 lg:opacity-0 lg:group-hover:opacity-100">
                          {source.status === "failed" ? (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-8"
                              aria-label={`重试 ${source.display_name}`}
                              disabled={isRetrying}
                              onClick={() => onRetry(source.id)}
                            >
                              <RotateCcw className="size-4" />
                            </Button>
                          ) : null}
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-muted-foreground hover:text-destructive"
                            aria-label={`删除 ${source.display_name}`}
                            disabled={isDeleting}
                            onClick={() => onDelete(source.id)}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </>
            ) : null}
            {!isLoading && !sources?.length ? (
              <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center">
                <span className="inline-flex size-10 items-center justify-center rounded-full bg-muted">
                  <FileText className="size-5 text-muted-foreground" />
                </span>
                <p className="text-sm font-medium">还没有资料</p>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  上传 PDF、TXT 或 Markdown，
                  <br />
                  解析完成后即可检索提问。
                </p>
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  )
}
