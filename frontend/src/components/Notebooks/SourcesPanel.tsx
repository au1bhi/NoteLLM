import {
  File,
  FileText,
  Loader2,
  RotateCcw,
  Trash2,
  Upload,
} from "lucide-react"
import { type ChangeEvent, useRef } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { Source } from "@/services/notebooks"

interface SourcesPanelProps {
  sources?: Source[]
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

export function SourcesPanel({
  sources,
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
}: SourcesPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const [file] = Array.from(event.target.files ?? [])
    if (file) onUploadFile(file)
    event.target.value = ""
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

      <div className="p-4">
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
          <ul className="space-y-2">
            {sources.map((source) => {
              const { Icon, tone } = fileTone(source.media_type)
              return (
                <li
                  key={source.id}
                  className="group flex items-center gap-3 rounded-lg border bg-background p-3 transition-colors hover:bg-muted/40"
                >
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
      </div>
    </section>
  )
}
