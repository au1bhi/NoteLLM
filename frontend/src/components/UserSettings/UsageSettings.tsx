import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { Coins, Gauge, KeyRound } from "lucide-react"
import type { ComponentType } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import { usageApi } from "@/services/usage"
import { extractErrorMessage } from "@/utils"

type BillingSource = "server" | "user" | "none"

function formatNumber(value: number): string {
  return value.toLocaleString("zh-CN")
}

function SourceBadge({ source }: { source?: BillingSource }) {
  if (source === "user") {
    return (
      <Badge
        variant="outline"
        className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
      >
        <KeyRound className="size-3" />
        使用自己的 API Key
      </Badge>
    )
  }
  if (source === "server") {
    return (
      <Badge
        variant="outline"
        className="border-primary/30 bg-primary/10 text-primary"
      >
        服务端免费额度计费
      </Badge>
    )
  }
  return (
    <Badge
      variant="outline"
      className="border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400"
    >
      尚未配置
    </Badge>
  )
}

function QuotaBar({ used, quota }: { used: number; quota: number }) {
  const pct = Math.min(100, Math.round((used / quota) * 100))
  const over = used >= quota
  const tone = over
    ? "bg-destructive"
    : pct >= 80
      ? "bg-amber-500"
      : "bg-emerald-500"
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          已用 {formatNumber(used)} / {formatNumber(quota)}
        </span>
        <span
          className={cn(
            "font-medium tabular-nums",
            over ? "text-destructive" : "text-muted-foreground",
          )}
        >
          {over ? "已用完" : `${pct}%`}
        </span>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", tone)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  quota,
  source,
}: {
  icon: ComponentType<{ className?: string }>
  label: string
  value: number
  quota?: number | null
  source?: BillingSource
}) {
  return (
    <div className="flex flex-col gap-4 rounded-xl border bg-card p-5 shadow-soft transition-shadow hover:shadow-card">
      <div className="flex items-start justify-between gap-3">
        <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-gradient-soft text-primary">
          <Icon className="size-5" />
        </span>
        <SourceBadge source={source} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-semibold tracking-tight tabular-nums">
          {formatNumber(value)}
        </p>
        <p className="truncate text-sm text-muted-foreground">{label}</p>
      </div>
      {typeof quota === "number" ? (
        <QuotaBar used={value} quota={quota} />
      ) : (
        <p className="text-xs leading-relaxed text-muted-foreground/80">
          {source === "none"
            ? "未配置该模型，无法使用。请到“模型配置”填入 API Key，或等待服务端配置默认模型。"
            : "使用自己的 API Key，用量计在你的密钥上，不消耗免费额度。"}
        </p>
      )}
    </div>
  )
}

export function UsageSettings() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["user-usage"],
    queryFn: usageApi.get,
  })

  const nearLimit =
    (typeof data?.chat_quota === "number" &&
      data.chat_tokens / data.chat_quota >= 0.8) ||
    (typeof data?.embedding_quota === "number" &&
      data.embedding_chars / data.embedding_quota >= 0.8)

  return (
    <div className="max-w-2xl">
      <div className="flex flex-col gap-2 rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 text-sm text-muted-foreground">
        <p>
          免费额度按自然月刷新，只统计使用服务端密钥的用量。如果你在“模型配置”
          中填入自己的 API Key，对应维度将不再消耗免费额度。
        </p>
        {data ? (
          <p className="text-xs text-muted-foreground/80">
            当前额度周期：
            {data.period_start ? data.period_start.slice(0, 7) : ""}（每月 1
            日重置）
          </p>
        ) : null}
      </div>

      {isLoading ? (
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-44 rounded-xl" />
          <Skeleton className="h-44 rounded-xl" />
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
            quota={data.chat_quota}
            source={data.chat_source}
          />
          <StatCard
            icon={Gauge}
            label="嵌入字符消耗"
            value={data.embedding_chars}
            quota={data.embedding_quota}
            source={data.embedding_source}
          />
        </div>
      ) : null}

      {data?.chat_source === "none" || data?.embedding_source === "none" ? (
        <div className="mt-5 flex items-center justify-between gap-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm">
          <p className="text-amber-700 dark:text-amber-400">
            尚未配置对话或嵌入模型，问答、上传与检索暂时不可用。
          </p>
          <Button asChild size="sm" variant="outline" className="shrink-0">
            <Link to="/settings" search={{ tab: "model" }}>
              去配置
            </Link>
          </Button>
        </div>
      ) : null}

      {nearLimit ? (
        <div className="mt-5 flex items-center justify-between gap-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm">
          <p className="text-amber-700 dark:text-amber-400">
            免费额度即将用完（已用
            ≥80%），用尽后将暂时无法使用服务端计费的对话或嵌入功能。
          </p>
          <Button asChild size="sm" variant="outline" className="shrink-0">
            <Link to="/settings" search={{ tab: "model" }}>
              配置自己的 Key
            </Link>
          </Button>
        </div>
      ) : null}
    </div>
  )
}
