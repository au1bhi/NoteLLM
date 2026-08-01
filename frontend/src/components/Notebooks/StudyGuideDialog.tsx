import { useMutation } from "@tanstack/react-query"
import { BookOpenText, Copy, Loader2, RefreshCw } from "lucide-react"
import { useState } from "react"

import type { StudyGuidePublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { useCopyToClipboard } from "@/hooks/useCopyToClipboard"
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { notebooksApi } from "@/services/notebooks"
import { extractErrorMessage } from "@/utils"
import { Markdown } from "./Markdown"

function guideToMarkdown(guide: StudyGuidePublic): string {
  const sections = guide.sections
    .map((section) => `## ${section.title}\n\n${section.content}`)
    .join("\n\n")
  const faqs = guide.faqs
    .map((faq) => `### 问：${faq.question}\n\n答：${faq.answer}`)
    .join("\n\n")
  return [sections, faqs ? `## 常见问题\n\n${faqs}` : ""]
    .filter(Boolean)
    .join("\n\n")
}

interface StudyGuideDialogProps {
  notebookId: string
  hasReadySources: boolean
}

export function StudyGuideDialog({
  notebookId,
  hasReadySources,
}: StudyGuideDialogProps) {
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [, copy] = useCopyToClipboard()
  const [guide, setGuide] = useState<StudyGuidePublic | null>(null)

  const mutation = useMutation({
    mutationFn: () => notebooksApi.generateStudyGuide(notebookId),
    onError: (error: Error) => showErrorToast(extractErrorMessage(error)),
    onSuccess: setGuide,
  })

  const copyGuide = async () => {
    if (!guide) return
    await copy(guideToMarkdown(guide))
    showSuccessToast("已复制为 Markdown")
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={!hasReadySources || mutation.isPending}
          onClick={() => {
            if (!mutation.data) mutation.mutate()
          }}
        >
          {mutation.isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <BookOpenText className="size-4" />
          )}
          学习指南
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BookOpenText className="size-5 text-primary" />
            学习指南
          </DialogTitle>
          <DialogDescription>
            基于当前笔记本资料生成的学习要点与常见问题。
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-3">
          <Button
            variant="ghost"
            size="sm"
            disabled={mutation.isPending || !guide}
            onClick={() => mutation.mutate()}
          >
            <RefreshCw
              className={cn("size-3.5", mutation.isPending && "animate-spin")}
            />
            重新生成
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!guide}
            onClick={() => void copyGuide()}
          >
            <Copy className="size-3.5" />
            复制 Markdown
          </Button>
        </div>

        {mutation.isPending ? (
          <div className="space-y-4">
            <Skeleton className="h-5 w-1/3" />
            <Skeleton className="h-24 rounded-lg" />
            <Skeleton className="h-5 w-1/4" />
            <Skeleton className="h-24 rounded-lg" />
          </div>
        ) : null}
        {mutation.error ? (
          <p className="text-sm text-destructive">
            {extractErrorMessage(mutation.error)}
          </p>
        ) : null}
        {guide ? (
          <div className="space-y-6">
            {guide.sections.map((section) => (
              <div key={section.title}>
                <h3 className="text-base font-semibold tracking-tight">
                  {section.title}
                </h3>
                <div className="mt-1">
                  <Markdown content={section.content} />
                </div>
              </div>
            ))}
            {guide.faqs.length ? (
              <div>
                <h3 className="text-base font-semibold tracking-tight">
                  常见问题
                </h3>
                <div className="mt-2 space-y-3">
                  {guide.faqs.map((faq) => (
                    <div
                      key={faq.question}
                      className="rounded-lg border bg-muted/40 p-3"
                    >
                      <p className="text-sm font-medium">问：{faq.question}</p>
                      <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                        答：{faq.answer}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
