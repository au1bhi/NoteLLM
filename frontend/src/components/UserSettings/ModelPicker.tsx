import { useMutation } from "@tanstack/react-query"
import { ChevronsUpDown, Loader2, RefreshCw, Search, Wand2 } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { providerSettingsApi } from "@/services/provider-settings"

interface ModelPickerProps {
  value: string
  baseUrl: string
  apiKey: string
  onValueChange: (value: string) => void
}

export function ModelPicker({
  value,
  baseUrl,
  apiKey,
  onValueChange,
}: ModelPickerProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [manual, setManual] = useState(false)

  const fetchMutation = useMutation({
    mutationFn: () => providerSettingsApi.fetchModels(baseUrl, apiKey),
  })

  const models = fetchMutation.data?.map((model) => model.id) ?? []
  const filtered = models.filter((model) =>
    model.toLowerCase().includes(query.toLowerCase()),
  )
  const canFetch = Boolean(baseUrl.trim() && apiKey.trim())

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className="w-full justify-between font-normal"
        >
          <span className={value ? "truncate" : "text-muted-foreground"}>
            {value || "选择或输入模型"}
          </span>
          <ChevronsUpDown className="size-4 shrink-0 opacity-50" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>选择模型</DialogTitle>
        </DialogHeader>

        <div className="flex items-center gap-2 rounded-md border bg-background px-3">
          <Search className="size-4 shrink-0 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索模型…"
            className="h-9 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>

        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {models.length
              ? `已获取 ${models.length} 个模型`
              : "填入 Base URL 与 API Key 后即可获取"}
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!canFetch || fetchMutation.isPending}
            onClick={() => fetchMutation.mutate()}
          >
            {fetchMutation.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
            获取模型
          </Button>
        </div>
        {fetchMutation.isError ? (
          <p className="text-xs text-destructive">
            {fetchMutation.error.message}
          </p>
        ) : null}

        {filtered.length ? (
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {filtered.map((model) => (
              <button
                key={model}
                type="button"
                onClick={() => {
                  onValueChange(model)
                  setOpen(false)
                }}
                className={cn(
                  "block w-full rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-muted",
                  model === value && "bg-primary/10 font-medium text-primary",
                )}
              >
                {model}
              </button>
            ))}
          </div>
        ) : null}

        {!filtered.length && !fetchMutation.isPending ? (
          <div className="space-y-2 rounded-lg border border-dashed p-4 text-center">
            <p className="text-sm text-muted-foreground">没有可用模型</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setManual(true)}
            >
              <Wand2 className="size-3.5" />
              手动输入模型名
            </Button>
          </div>
        ) : null}

        {manual ? (
          <div className="space-y-2">
            <Input
              value={value}
              onChange={(event) => onValueChange(event.target.value)}
              placeholder="例如 gpt-4o-mini"
              autoFocus
            />
            <Button
              type="button"
              size="sm"
              className="w-full"
              onClick={() => setOpen(false)}
            >
              确定
            </Button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
