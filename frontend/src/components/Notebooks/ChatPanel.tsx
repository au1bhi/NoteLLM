import {
  Loader2,
  MessageSquarePlus,
  MessagesSquare,
  Pencil,
  Send,
  Trash2,
} from "lucide-react"
import { type KeyboardEvent, useEffect, useRef, useState } from "react"

import type { ConversationMessagePublic, ConversationPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"
import type { AnswerMode } from "@/services/conversations"
import { sortPinnedFirst } from "@/utils"
import { Citations } from "./Citations"
import { Markdown } from "./Markdown"
import { PinButton } from "./PinButton"
import { StudyPlanDialog } from "./StudyPlanDialog"

const ANSWER_MODES: { value: AnswerMode; label: string; hint: string }[] = [
  {
    value: "grounded",
    label: "仅依据资料",
    hint: "回答只基于当前笔记本中已就绪的资料，并附上可追溯来源。",
  },
  {
    value: "hybrid",
    label: "资料 + 已有知识",
    hint: "回答优先基于当前笔记本的资料，可结合已有知识补充。",
  },
  {
    value: "knowledge",
    label: "自由问答",
    hint: "使用通用知识直接回答，不依赖笔记本中的资料。",
  },
]

const DEFAULT_STARTERS = [
  "总结这份资料的核心内容",
  "这份资料讲了什么？",
  "有哪些关键概念？",
  "用三句话概括主要观点",
]

function StarterChips({ onPick }: { onPick: (question: string) => void }) {
  return (
    <div className="mt-4 flex flex-wrap justify-center gap-2">
      {DEFAULT_STARTERS.map((question) => (
        <button
          key={question}
          type="button"
          onClick={() => onPick(question)}
          className="rounded-full border bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          {question}
        </button>
      ))}
    </div>
  )
}

interface ChatPanelProps {
  messages?: ConversationMessagePublic[]
  conversations: ConversationPublic[]
  activeConversationId: string | null
  isConversationLoading: boolean
  isStreaming: boolean
  streamingAnswer: string
  hasReadySources: boolean
  onCreatePending: boolean
  isRenaming: boolean
  pinPending?: boolean
  sourceScope?: string
  className?: string
  onNewConversation: () => void
  onSelectConversation: (id: string) => void
  onRenameConversation: (conversationId: string, title: string) => void
  onPinConversation: (conversationId: string, isPinned: boolean) => void
  onDeleteConversation: (conversationId: string) => void
  isDeleting?: boolean
  onSend: (content: string, mode: AnswerMode) => void
}

function MessageBubble({
  message,
  onPickSuggestion,
}: {
  message: ConversationMessagePublic
  onPickSuggestion?: (question: string) => void
}) {
  if (message.role === "user") {
    return (
      <div className="ml-auto max-w-[85%]">
        <div className="rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-soft">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
      </div>
    )
  }
  return (
    <div className="mr-auto max-w-full">
      <div className="rounded-2xl rounded-bl-md border bg-background p-4 shadow-soft">
        <Markdown content={message.content} />
        <Citations citations={message.citations} />
        <Suggestions
          suggestions={message.suggestions}
          onPick={onPickSuggestion}
        />
      </div>
    </div>
  )
}

function Suggestions({
  suggestions,
  onPick,
}: {
  suggestions?: string[]
  onPick?: (question: string) => void
}) {
  if (!suggestions?.length || !onPick) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2 border-t pt-3">
      {suggestions.map((question, index) => (
        <button
          key={`${index}-${question}`}
          type="button"
          onClick={() => onPick(question)}
          className="rounded-full border bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
        >
          {question}
        </button>
      ))}
    </div>
  )
}

function StreamingBubble({ text }: { text: string }) {
  return (
    <div className="mr-auto max-w-full">
      <div className="rounded-2xl rounded-bl-md border bg-background p-4 shadow-soft">
        {text ? (
          <>
            <Markdown content={text} />
            <span
              aria-hidden="true"
              className="ml-1 inline-block h-4 w-1.5 animate-caret rounded-sm bg-primary align-middle"
            />
          </>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            正在检索资料并生成回答…
          </p>
        )}
      </div>
    </div>
  )
}

export function ChatPanel({
  messages,
  conversations,
  activeConversationId,
  isConversationLoading,
  isStreaming,
  streamingAnswer,
  hasReadySources,
  onCreatePending,
  isRenaming,
  pinPending,
  sourceScope,
  className,
  onNewConversation,
  onSelectConversation,
  onRenameConversation,
  onPinConversation,
  onDeleteConversation,
  isDeleting,
  onSend,
}: ChatPanelProps) {
  const [question, setQuestion] = useState("")
  const [mode, setMode] = useState<AnswerMode>("grounded")
  const [renameOpen, setRenameOpen] = useState(false)
  const [renameTitle, setRenameTitle] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<ConversationPublic | null>(
    null,
  )
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeConversationId,
  )
  const activeMode = ANSWER_MODES.find((item) => item.value === mode)

  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional — keep scrolled to the latest message while messages arrive or stream
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight })
  }, [messages, streamingAnswer, isStreaming, activeConversationId])

  // biome-ignore lint/correctness/useExhaustiveDependencies: intentional — resize the composer as the question grows
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`
  }, [question])

  const canSend =
    Boolean(activeConversationId) && !isStreaming && Boolean(question.trim())

  const handleSend = () => {
    if (!canSend) return
    const content = question.trim()
    setQuestion("")
    onSend(content, mode)
  }

  const pickSuggestion = (question: string) => {
    if (isStreaming || !activeConversationId) return
    onSend(question, mode)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault()
      handleSend()
    }
  }

  const openRename = () => {
    if (!activeConversation) return
    setRenameTitle(activeConversation.title || "")
    setRenameOpen(true)
  }

  const submitRename = () => {
    const title = renameTitle.trim()
    if (!title || !activeConversationId || isRenaming) return
    onRenameConversation(activeConversationId, title)
    setRenameOpen(false)
  }

  return (
    <section
      className={cn(
        "flex min-h-[30rem] flex-col overflow-hidden rounded-xl border bg-card shadow-soft lg:h-[calc(100svh-16rem)]",
        className,
      )}
    >
      <header className="border-b px-4 py-3.5">
        <div className="flex items-center gap-2">
          <h2 className="min-w-0 truncate font-semibold tracking-tight">
            {activeConversation ? activeConversation.title : "问答"}
          </h2>
          {activeConversation ? (
            <Button
              variant="ghost"
              size="icon"
              className="size-7 shrink-0 rounded-md text-muted-foreground hover:text-foreground"
              aria-label="重命名会话"
              onClick={openRename}
            >
              <Pencil className="size-3.5" />
            </Button>
          ) : null}
          {activeConversation ? (
            <PinButton
              pinned={Boolean(activeConversation.is_pinned)}
              disabled={pinPending}
              className="size-7 shrink-0 rounded-md text-muted-foreground hover:text-foreground"
              onToggle={() =>
                onPinConversation(
                  activeConversation.id,
                  !activeConversation.is_pinned,
                )
              }
            />
          ) : null}
          {activeConversation ? (
            <StudyPlanDialog
              conversationId={activeConversation.id}
              hasConversationContent={Boolean(messages?.length)}
              disabled={isStreaming}
            />
          ) : null}
          <Button
            variant="outline"
            size="sm"
            className="ml-auto shrink-0"
            disabled={onCreatePending || isStreaming || !hasReadySources}
            title={
              hasReadySources ? undefined : "至少上传一份资料并处理完成后再提问"
            }
            onClick={onNewConversation}
          >
            {onCreatePending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <MessageSquarePlus className="size-4" />
            )}
            新建会话
          </Button>
        </div>
        {conversations.length ? (
          <div className="mt-3 flex gap-2 overflow-x-auto pb-0.5">
            {sortPinnedFirst(conversations).map((conversation) => (
              <div key={conversation.id} className="group relative shrink-0">
                <Button
                  size="sm"
                  variant={
                    activeConversationId === conversation.id
                      ? "default"
                      : "outline"
                  }
                  className="pr-8"
                  disabled={isStreaming}
                  onClick={() => onSelectConversation(conversation.id)}
                >
                  {conversation.title || "会话"}
                </Button>
                <button
                  type="button"
                  aria-label={`删除会话：${conversation.title || "未命名"}`}
                  disabled={isStreaming || isDeleting}
                  onClick={() => setDeleteTarget(conversation)}
                  className="absolute right-1 top-1/2 flex size-5 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground/70 transition-colors opacity-0 hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100 max-sm:opacity-100"
                >
                  <Trash2 className="size-3" />
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </header>

      <div
        ref={scrollRef}
        className="flex-1 space-y-4 overflow-y-auto p-4 md:p-5"
      >
        {isConversationLoading ? (
          <div className="space-y-4">
            <Skeleton className="ml-auto h-10 w-2/3 rounded-2xl" />
            <Skeleton className="h-28 w-11/12 rounded-2xl" />
          </div>
        ) : null}

        {!isConversationLoading && !activeConversationId ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-10 text-center">
            <span className="inline-flex size-12 items-center justify-center rounded-2xl bg-brand-gradient-soft text-primary">
              <MessagesSquare className="size-6" />
            </span>
            <div>
              <p className="font-semibold">开始一次问答</p>
              <p className="mx-auto mt-1 max-w-xs text-sm text-muted-foreground">
                {hasReadySources
                  ? "新建一个会话，或从上方选择一个既有会话继续提问。"
                  : "至少上传一份资料并等它处理完成，才能开始有依据的问答。"}
              </p>
            </div>
            {hasReadySources ? (
              <Button size="sm" onClick={onNewConversation}>
                <MessageSquarePlus className="size-4" />
                新建会话
              </Button>
            ) : null}
          </div>
        ) : null}

        {messages?.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onPickSuggestion={pickSuggestion}
          />
        ))}

        {isStreaming ? <StreamingBubble text={streamingAnswer} /> : null}

        {!isConversationLoading &&
        activeConversationId &&
        !isStreaming &&
        !messages?.length ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 py-10 text-center">
            <p className="text-sm text-muted-foreground">
              还没有消息，试着问一个关于资料的问题。
            </p>
            {hasReadySources ? <StarterChips onPick={pickSuggestion} /> : null}
          </div>
        ) : null}
      </div>

      <div className="border-t bg-muted/40 p-3">
        <div className="mb-2 flex flex-wrap items-center gap-1.5">
          {ANSWER_MODES.map((item) => (
            <button
              key={item.value}
              type="button"
              aria-pressed={mode === item.value}
              disabled={!activeConversationId || isStreaming}
              onClick={() => setMode(item.value)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
                mode === item.value
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground",
                (!activeConversationId || isStreaming) && "opacity-60",
              )}
            >
              {item.label}
            </button>
          ))}
          {sourceScope ? (
            <span className="ml-auto text-xs text-muted-foreground">
              {sourceScope}
            </span>
          ) : null}
        </div>
        <div className="flex items-end gap-1.5 rounded-2xl border bg-background p-1.5 pl-3.5 shadow-soft transition-all focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/25">
          <textarea
            ref={textareaRef}
            rows={1}
            value={question}
            disabled={!activeConversationId || isStreaming}
            aria-label="输入问题"
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              activeConversationId
                ? isStreaming
                  ? "正在生成回答…"
                  : hasReadySources
                    ? "基于当前笔记本的资料提问…"
                    : "资料处理完成后即可提问…"
                : "先选择或新建一个会话"
            }
            className={cn(
              "max-h-48 min-h-10 flex-1 resize-none border-0 bg-transparent px-0 py-2.5 text-sm outline-none placeholder:text-muted-foreground",
              isStreaming && "opacity-60",
            )}
          />
          <Button
            size="icon"
            className="size-9 shrink-0 rounded-xl bg-primary text-primary-foreground shadow-soft hover:opacity-95"
            disabled={!canSend}
            aria-label="发送问题"
            onClick={handleSend}
          >
            <Send className="size-4" />
          </Button>
        </div>
        <p className="mt-2 text-center text-xs text-muted-foreground">
          {activeMode?.hint}
        </p>
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>重命名会话</DialogTitle>
            <DialogDescription>
              为当前会话起一个更容易识别的名字。
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              submitRename()
            }}
            className="grid gap-4"
          >
            <Input
              autoFocus
              value={renameTitle}
              placeholder="会话标题"
              onChange={(event) => setRenameTitle(event.target.value)}
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={isRenaming}>
                  取消
                </Button>
              </DialogClose>
              <Button
                type="submit"
                disabled={isRenaming || !renameTitle.trim()}
              >
                {isRenaming ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : null}
                保存
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>删除会话</DialogTitle>
            <DialogDescription>
              将删除“{deleteTarget?.title || "未命名"}
              ”及其全部消息。若该会话已有学习计划，计划与任务也会一并删除，此操作不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" disabled={isDeleting}>
                取消
              </Button>
            </DialogClose>
            <Button
              variant="destructive"
              disabled={isDeleting}
              onClick={() => {
                if (!deleteTarget) return
                const id = deleteTarget.id
                setDeleteTarget(null)
                onDeleteConversation(id)
              }}
            >
              {isDeleting ? <Loader2 className="size-4 animate-spin" /> : null}
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
