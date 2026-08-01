import { useQuery } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import {
  BookOpen,
  CheckCircle2,
  FileText,
  KeyRound,
  MessagesSquare,
  X,
} from "lucide-react"
import { useState } from "react"

import { AddNotebook } from "@/components/Notebooks/AddNotebook"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { usageApi } from "@/services/usage"

const STORAGE_KEY = "notellm-onboarding-dismissed"

export interface OnboardingChecklistProps {
  notebooksCount: number
  readySourcesCount: number
  conversationsCount: number
  firstNotebookId?: string
}

interface Step {
  id: "model" | "notebook" | "source" | "question"
  icon: typeof KeyRound
  title: string
  description: string
}

const STEPS: Step[] = [
  {
    id: "model",
    icon: KeyRound,
    title: "配置模型",
    description:
      "填入自己的对话与嵌入模型 API Key，或使用服务端已配置的默认模型。",
  },
  {
    id: "notebook",
    icon: BookOpen,
    title: "创建笔记本",
    description: "为每门课程或研究主题建一个专属笔记本。",
  },
  {
    id: "source",
    icon: FileText,
    title: "上传资料",
    description: "放入讲义、论文或笔记，支持 PDF、TXT 与 Markdown。",
  },
  {
    id: "question",
    icon: MessagesSquare,
    title: "开始提问",
    description: "在资料范围内提问，获得带引用的可验证答案。",
  },
]

function StepRow({
  step,
  done,
  cta,
}: {
  step: Step
  done: boolean
  cta: React.ReactNode
}) {
  const Icon = step.icon
  return (
    <li className="flex items-center gap-4">
      <span
        className={cn(
          "inline-flex size-10 shrink-0 items-center justify-center rounded-xl",
          done
            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            : "bg-brand-gradient-soft text-primary",
        )}
      >
        {done ? (
          <CheckCircle2 className="size-5" />
        ) : (
          <Icon className="size-5" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          {step.title}
          {done ? (
            <span className="text-xs font-normal text-emerald-600 dark:text-emerald-400">
              已完成
            </span>
          ) : null}
        </h3>
        <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">
          {step.description}
        </p>
      </div>
      {!done ? <div className="shrink-0">{cta}</div> : null}
    </li>
  )
}

export function OnboardingChecklist({
  notebooksCount,
  readySourcesCount,
  conversationsCount,
  firstNotebookId,
}: OnboardingChecklistProps) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(STORAGE_KEY) === "1",
  )
  const { data: usage } = useQuery({
    queryKey: ["user-usage"],
    queryFn: usageApi.get,
  })

  if (dismissed) {
    return null
  }

  // Model step is done once both dimensions have a working provider.
  const modelConfigured =
    !!usage && usage.chat_source !== "none" && usage.embedding_source !== "none"
  const stepStates = {
    model: modelConfigured,
    notebook: notebooksCount > 0,
    source: readySourcesCount > 0,
    question: conversationsCount > 0,
  }
  const allDone = Object.values(stepStates).every(Boolean)
  if (allDone) {
    return null
  }

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, "1")
    setDismissed(true)
  }

  return (
    <section className="relative overflow-hidden rounded-2xl border bg-card p-6 shadow-soft">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-tight">
            快速上手
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            完成下面几步，开始你的第一个有依据的问答。之后可随时在“设置”里调整。
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="text-muted-foreground"
          aria-label="稍后再说"
          onClick={dismiss}
        >
          <X className="size-4" />
        </Button>
      </div>

      <ol className="mt-6 space-y-5">
        <StepRow
          step={STEPS[0]}
          done={stepStates.model}
          cta={
            <Button asChild size="sm" variant="outline">
              <Link to="/settings" search={{ tab: "model" }}>
                去配置
              </Link>
            </Button>
          }
        />
        <StepRow
          step={STEPS[1]}
          done={stepStates.notebook}
          cta={<AddNotebook compact />}
        />
        <StepRow
          step={STEPS[2]}
          done={stepStates.source}
          cta={
            firstNotebookId ? (
              <Button asChild size="sm" variant="outline">
                <Link
                  to="/notebooks/$notebookId"
                  params={{ notebookId: firstNotebookId }}
                >
                  去上传
                </Link>
              </Button>
            ) : (
              <Button asChild size="sm" variant="outline">
                <Link to="/notebooks">去上传</Link>
              </Button>
            )
          }
        />
        <StepRow
          step={STEPS[3]}
          done={stepStates.question}
          cta={
            firstNotebookId ? (
              <Button asChild size="sm" variant="outline">
                <Link
                  to="/notebooks/$notebookId"
                  params={{ notebookId: firstNotebookId }}
                >
                  去提问
                </Link>
              </Button>
            ) : null
          }
        />
      </ol>

      <p className="mt-6 text-xs text-muted-foreground/70">
        免费用户每月享有 10 万 token 对话额度与 30 万字符嵌入额度；配置自己的
        API Key 后对应维度不再消耗免费额度。
      </p>
    </section>
  )
}
