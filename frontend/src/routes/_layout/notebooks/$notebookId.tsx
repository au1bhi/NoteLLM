import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import {
  ArrowLeft,
  NotebookPen,
  PanelRight,
  PanelRightClose,
} from "lucide-react"
import { useState } from "react"

import type { ConversationMessagePublic } from "@/client"
import { ChatPanel } from "@/components/Notebooks/ChatPanel"
import { DeleteNotebook } from "@/components/Notebooks/DeleteNotebook"
import { EditNotebook } from "@/components/Notebooks/EditNotebook"
import { NotebookOverview } from "@/components/Notebooks/NotebookOverview"
import { SourcesPanel } from "@/components/Notebooks/SourcesPanel"
import { StudyGuideDialog } from "@/components/Notebooks/StudyGuideDialog"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { useIsDesktop } from "@/hooks/useMobile"
import {
  type AnswerMode,
  type ConversationDetail,
  conversationsApi,
} from "@/services/conversations"
import { notebooksApi } from "@/services/notebooks"

export const Route = createFileRoute("/_layout/notebooks/$notebookId")({
  component: NotebookWorkspace,
  head: () => ({ meta: [{ title: "Notebook - NoteLLM" }] }),
})

function NotebookWorkspace() {
  const { notebookId } = Route.useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const isDesktop = useIsDesktop()
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [streamingAnswer, setStreamingAnswer] = useState("")
  const [isStreaming, setIsStreaming] = useState(false)
  const [sourcesOpen, setSourcesOpen] = useState(true)
  const [mobileSourcesOpen, setMobileSourcesOpen] = useState(false)
  const [selectedSourceIds, setSelectedSourceIds] = useState<Set<string>>(
    new Set(),
  )

  const toggleSource = (sourceId: string) => {
    setSelectedSourceIds((prev) => {
      const next = new Set(prev)
      if (prev.size === 0) {
        next.add(sourceId)
        return next
      }
      if (next.has(sourceId)) {
        next.delete(sourceId)
        return next
      }
      next.add(sourceId)
      return next
    })
  }
  const selectAllSources = () => setSelectedSourceIds(new Set())

  const notebook = useQuery({
    queryFn: () => notebooksApi.get(notebookId),
    queryKey: ["notebooks", notebookId],
  })
  const sources = useQuery({
    queryFn: () => notebooksApi.listSources(notebookId),
    queryKey: ["notebooks", notebookId, "sources"],
    refetchInterval: (query) =>
      query.state.data?.data.some((source) => source.status === "processing")
        ? 2000
        : false,
  })
  const conversations = useQuery({
    queryFn: () => conversationsApi.list(notebookId),
    queryKey: ["notebooks", notebookId, "conversations"],
  })
  const conversation = useQuery({
    enabled: Boolean(conversationId),
    queryFn: () => conversationsApi.get(conversationId as string),
    queryKey: ["conversations", conversationId],
  })

  const createConversationMutation = useMutation({
    mutationFn: () => conversationsApi.create(notebookId),
    onError: (error: Error) => showErrorToast(error.message),
    onSuccess: (created) => {
      setConversationId(created.id)
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "conversations"],
      })
    },
  })
  const uploadMutation = useMutation({
    mutationFn: (file: File) => notebooksApi.uploadSource(notebookId, file),
    onError: (error: Error) => showErrorToast(error.message),
    onSuccess: (source) => {
      if (source.status === "ready") {
        showSuccessToast("Source processed successfully")
      } else if (source.status === "processing") {
        showSuccessToast("Source uploaded, processing…")
      } else {
        showErrorToast(source.error_message || "Source could not be processed")
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "sources"],
      })
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "overview"],
      })
    },
  })
  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) =>
      notebooksApi.deleteSource(notebookId, sourceId),
    onError: (error: Error) => showErrorToast(error.message),
    onSuccess: () => showSuccessToast("Source deleted"),
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "sources"],
      })
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "overview"],
      })
    },
  })
  const retryMutation = useMutation({
    mutationFn: (sourceId: string) =>
      notebooksApi.retrySource(notebookId, sourceId),
    onError: (error: Error) => showErrorToast(error.message),
    onSuccess: (source) => {
      if (source.status === "ready") {
        showSuccessToast("Source processed successfully")
      } else if (source.status === "processing") {
        showSuccessToast("Source is processing…")
      } else {
        showErrorToast(source.error_message || "Source could not be processed")
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "sources"],
      })
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "overview"],
      })
    },
  })
  const renameConversationMutation = useMutation({
    mutationFn: ({
      conversationId,
      title,
    }: {
      conversationId: string
      title: string
    }) => conversationsApi.update(conversationId, title),
    onError: (error: Error) => showErrorToast(error.message),
    onSuccess: (_, variables) => {
      showSuccessToast("会话已重命名")
      queryClient.invalidateQueries({
        queryKey: ["conversations", variables.conversationId],
      })
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "conversations"],
      })
    },
  })

  const sendQuestion = async (
    content: string,
    mode: AnswerMode = "grounded",
  ) => {
    if (!conversationId) return
    const optimisticMessage: ConversationMessagePublic = {
      id: `temp-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
      citations: [],
    }
    queryClient.setQueryData<ConversationDetail>(
      ["conversations", conversationId],
      (old) =>
        old ? { ...old, messages: [...old.messages, optimisticMessage] } : old,
    )
    setStreamingAnswer("")
    setIsStreaming(true)
    try {
      await conversationsApi.stream(conversationId, content, {
        mode,
        sourceIds: selectedSourceIds.size ? [...selectedSourceIds] : undefined,
        onCitations: () => undefined,
        onDelta: (text) => setStreamingAnswer((answer) => answer + text),
      })
      await queryClient.invalidateQueries({
        queryKey: ["conversations", conversationId],
      })
      await queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "conversations"],
      })
    } catch (error) {
      showErrorToast(error instanceof Error ? error.message : "Answer failed")
      await queryClient.invalidateQueries({
        queryKey: ["conversations", conversationId],
      })
    } finally {
      setIsStreaming(false)
      setStreamingAnswer("")
    }
  }

  const handleToggleSources = () => {
    if (!isDesktop) {
      setMobileSourcesOpen(true)
    } else {
      setSourcesOpen((open) => !open)
    }
  }

  if (notebook.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-96 rounded-xl" />
      </div>
    )
  }
  if (notebook.error) {
    return (
      <p className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        {notebook.error.message}
      </p>
    )
  }
  if (!notebook.data) {
    return null
  }

  const hasReadySources =
    sources.data?.data.some((source) => source.status === "ready") ?? false

  const sourcesPanel = (
    <SourcesPanel
      notebookId={notebookId}
      sources={sources.data?.data}
      selectedSourceIds={selectedSourceIds}
      isLoading={sources.isLoading}
      isError={Boolean(sources.error)}
      errorMessage={
        sources.error instanceof Error ? sources.error.message : undefined
      }
      isUploading={uploadMutation.isPending}
      isDeleting={deleteMutation.isPending}
      isRetrying={retryMutation.isPending}
      onUploadFile={(file) => uploadMutation.mutate(file)}
      onRetry={(sourceId) => retryMutation.mutate(sourceId)}
      onDelete={(sourceId) => deleteMutation.mutate(sourceId)}
      onToggleSource={toggleSource}
      onSelectAll={selectAllSources}
    />
  )

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Button variant="ghost" size="sm" asChild className="-ml-2 gap-1.5">
            <Link to="/notebooks">
              <ArrowLeft className="size-4" />
              笔记本
            </Link>
          </Button>
          <div className="mt-2 flex items-center gap-1.5">
            <h1 className="flex min-w-0 items-center gap-2.5 text-2xl font-bold tracking-tight">
              <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-gradient-soft text-primary">
                <NotebookPen className="size-4" />
              </span>
              <span className="truncate">{notebook.data.title}</span>
            </h1>
            <EditNotebook
              notebook={notebook.data}
              triggerClassName="size-8 shrink-0 rounded-lg text-muted-foreground hover:text-foreground"
            />
            <DeleteNotebook
              notebook={notebook.data}
              triggerClassName="size-8 shrink-0 rounded-lg text-muted-foreground hover:text-destructive"
              onDeleted={() => navigate({ to: "/notebooks" })}
            />
          </div>
          <p className="mt-1.5 line-clamp-2 text-muted-foreground">
            {notebook.data.description || "暂无描述"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StudyGuideDialog
            notebookId={notebookId}
            hasReadySources={hasReadySources}
          />
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={handleToggleSources}
          >
            {sourcesOpen && isDesktop ? (
              <PanelRightClose className="size-4" />
            ) : (
              <PanelRight className="size-4" />
            )}
            {isDesktop ? (sourcesOpen ? "隐藏资料" : "显示资料") : "资料"}
          </Button>
        </div>
      </div>

      <NotebookOverview
        notebookId={notebookId}
        hasReadySources={hasReadySources}
      />

      <div className="flex items-start gap-6">
        <ChatPanel
          messages={conversation.data?.messages}
          conversations={conversations.data?.data ?? []}
          activeConversationId={conversationId}
          isConversationLoading={
            Boolean(conversationId) && conversation.isLoading
          }
          isStreaming={isStreaming}
          streamingAnswer={streamingAnswer}
          hasReadySources={hasReadySources}
          onCreatePending={createConversationMutation.isPending}
          isRenaming={renameConversationMutation.isPending}
          sourceScope={
            selectedSourceIds.size === 0
              ? "全部资料"
              : `已选 ${selectedSourceIds.size} 个来源`
          }
          className="min-w-0 flex-1"
          onNewConversation={() => createConversationMutation.mutate()}
          onSelectConversation={setConversationId}
          onRenameConversation={(conversationId, title) =>
            renameConversationMutation.mutate({ conversationId, title })
          }
          onSend={(content, mode) => void sendQuestion(content, mode)}
        />

        {sourcesOpen ? (
          <aside className="hidden w-80 shrink-0 lg:block">
            <div className="sticky top-24">{sourcesPanel}</div>
          </aside>
        ) : null}
      </div>

      <Sheet open={mobileSourcesOpen} onOpenChange={setMobileSourcesOpen}>
        <SheetContent side="right" className="w-80 sm:w-80">
          <SheetHeader>
            <SheetTitle>资料</SheetTitle>
          </SheetHeader>
          <div className="mt-2">
            <SourcesPanel
              notebookId={notebookId}
              sources={sources.data?.data}
              selectedSourceIds={selectedSourceIds}
              isLoading={sources.isLoading}
              isError={Boolean(sources.error)}
              errorMessage={
                sources.error instanceof Error
                  ? sources.error.message
                  : undefined
              }
              isUploading={uploadMutation.isPending}
              isDeleting={deleteMutation.isPending}
              isRetrying={retryMutation.isPending}
              className="rounded-none border-0 shadow-none"
              onUploadFile={(file) => uploadMutation.mutate(file)}
              onRetry={(sourceId) => retryMutation.mutate(sourceId)}
              onDelete={(sourceId) => deleteMutation.mutate(sourceId)}
              onToggleSource={toggleSource}
              onSelectAll={selectAllSources}
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
