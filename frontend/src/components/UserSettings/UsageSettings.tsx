import { useQuery } from "@tanstack/react-query"
import { Coins, Gauge } from "lucide-react"
import type { ComponentType } from "react"

import { Skeleton } from "@/components/ui/skeleton"
import { usageApi } from "@/services/usage"
import { extractErrorMessage } from "@/utils"

function formatNumber(value: number): string {
  return value.toLocaleString("en-US")
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: ComponentType<{ className?: string }>
  label: string
  value: number
  hint: string
}) {
  return (
    <div className="flex items-center gap-4 rounded-xl border bg-card p-5 shadow-soft transition-shadow hover:shadow-card">
      <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-gradient-soft text-primary">
        <Icon className="size-5" />
      </span>
      <div className="min-w-0">
        <p className="text-2xl font-semibold tracking-tight tabular-nums">
          {formatNumber(value)}
        </p>
        <p className="truncate text-sm text-muted-foreground">{label}</p>
        <p className="text-xs text-muted-foreground/80">{hint}</p>
      </div>
    </div>
  )
}

export function UsageSettings() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["user-usage"],
    queryFn: usageApi.get,
  })

  return (
    <div className="max-w-2xl">
      <div className="rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 text-sm text-muted-foreground">
        这里统计你的模型 API 用量：对话 token 数与嵌入字符数。用量只在你实际
        调用模型时累计，清除后保留的历史记录仍在。
      </div>

      {isLoading ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-24 rounded-xl" />
        </div>
      ) : null}
      {error ? (
        <p className="mt-5 text-sm text-destructive">
          {extractErrorMessage(error)}
        </p>
      ) : null}
      {data ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <StatCard
            icon={Coins}
            label="对话 Token 消耗"
            value={data.chat_tokens}
            hint="流式回答 + 建议追问"
          />
          <StatCard
            icon={Gauge}
            label="嵌入字符消耗"
            value={data.embedding_chars}
            hint="上传资料 + 语义检索"
          />
        </div>
      ) : null}
    </div>
  )
}
