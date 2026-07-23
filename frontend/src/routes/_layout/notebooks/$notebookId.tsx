import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ArrowLeft,
  FileText,
  MessageSquarePlus,
  RotateCcw,
  Send,
  Trash2,
  Upload,
} from "lucide-react"
import { type ChangeEvent, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import useCustomToast from "@/hooks/useCustomToast"
import { conversationsApi } from "@/services/conversations"
import { notebooksApi } from "@/services/notebooks"

export const Route = createFileRoute("/_layout/notebooks/$notebookId")({
  component: NotebookWorkspace,
  head: () => ({ meta: [{ title: "Notebook - NoteLLM" }] }),
})

function NotebookWorkspace() {
  const { notebookId } = Route.useParams()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [question, setQuestion] = useState("")
  const [streamingAnswer, setStreamingAnswer] = useState("")
  const [isStreaming, setIsStreaming] = useState(false)
  const notebook = useQuery({
    queryFn: () => notebooksApi.get(notebookId),
    queryKey: ["notebooks", notebookId],
  })
  const sources = useQuery({
    queryFn: () => notebooksApi.listSources(notebookId),
    queryKey: ["notebooks", notebookId, "sources"],
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
      showSuccessToast(
        source.status === "ready"
          ? "Source processed successfully"
          : "Source uploaded but could not be processed",
      )
    },
    onSettled: () =>
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "sources"],
      }),
  })
  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) =>
      notebooksApi.deleteSource(notebookId, sourceId),
    onError: (error: Error) => showErrorToast(error.message),
    onSuccess: () => showSuccessToast("Source deleted"),
    onSettled: () =>
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "sources"],
      }),
  })
  const retryMutation = useMutation({
    mutationFn: (sourceId: string) =>
      notebooksApi.retrySource(notebookId, sourceId),
    onError: (error: Error) => showErrorToast(error.message),
    onSuccess: (source) =>
      showSuccessToast(
        source.status === "ready"
          ? "Source processed successfully"
          : "Source could not be processed",
      ),
    onSettled: () =>
      queryClient.invalidateQueries({
        queryKey: ["notebooks", notebookId, "sources"],
      }),
  })

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const [file] = Array.from(event.target.files ?? [])
    if (file) {
      uploadMutation.mutate(file)
    }
    event.target.value = ""
  }

  const sendQuestion = async () => {
    if (!conversationId || !question.trim()) return
    const content = question.trim()
    setQuestion("")
    setStreamingAnswer("")
    setIsStreaming(true)
    try {
      await conversationsApi.stream(conversationId, content, {
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
    } finally {
      setIsStreaming(false)
      setStreamingAnswer("")
    }
  }

  if (notebook.isLoading) {
    return <p className="text-muted-foreground">Loading notebook…</p>
  }
  if (notebook.error) {
    return <p className="text-destructive">{notebook.error.message}</p>
  }
  if (!notebook.data) {
    return null
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Button variant="ghost" asChild className="mb-3 -ml-3">
          <Link to="/notebooks">
            <ArrowLeft className="mr-2" />
            All notebooks
          </Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">
          {notebook.data.title}
        </h1>
        <p className="mt-1 text-muted-foreground">
          {notebook.data.description || "No description yet"}
        </p>
      </div>
      <section className="rounded-lg border p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="font-semibold">Sources</h2>
            <p className="text-sm text-muted-foreground">
              PDF, TXT, and Markdown files are processed into searchable chunks.
            </p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
            className="hidden"
            onChange={onFileChange}
          />
          <Button
            disabled={uploadMutation.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="mr-2" />
            {uploadMutation.isPending ? "Processing…" : "Upload source"}
          </Button>
        </div>
        {sources.isLoading ? (
          <p className="mt-4 text-sm">Loading sources…</p>
        ) : null}
        {sources.error ? (
          <p className="mt-4 text-sm text-destructive">
            {sources.error.message}
          </p>
        ) : null}
        {sources.data?.data.length ? (
          <ul className="mt-6 divide-y rounded-md border">
            {sources.data.data.map((source) => (
              <li
                key={source.id}
                className="flex items-center justify-between gap-4 p-4"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{source.display_name}</p>
                  <p className="text-sm text-muted-foreground">
                    {source.status === "ready"
                      ? `${source.char_count?.toLocaleString() ?? 0} characters processed`
                      : source.error_message || source.status}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  {source.status === "failed" ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Retry ${source.display_name}`}
                      disabled={retryMutation.isPending}
                      onClick={() => retryMutation.mutate(source.id)}
                    >
                      <RotateCcw className="size-4" />
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete ${source.display_name}`}
                    disabled={deleteMutation.isPending}
                    onClick={() => deleteMutation.mutate(source.id)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
        {sources.data?.data.length === 0 ? (
          <div className="mt-6 flex items-center gap-3 rounded-md bg-muted p-4 text-sm text-muted-foreground">
            <FileText className="size-5" />
            No sources have been uploaded yet.
          </div>
        ) : null}
      </section>
      <section className="rounded-lg border p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="font-semibold">Grounded conversation</h2>
            <p className="text-sm text-muted-foreground">
              Answers are limited to this notebook&apos;s processed sources.
            </p>
          </div>
          <Button
            variant="outline"
            disabled={createConversationMutation.isPending}
            onClick={() => createConversationMutation.mutate()}
          >
            <MessageSquarePlus className="mr-2" />
            New conversation
          </Button>
        </div>
        {conversations.data?.data.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {conversations.data.data.map((item) => (
              <Button
                key={item.id}
                size="sm"
                variant={conversationId === item.id ? "default" : "outline"}
                onClick={() => setConversationId(item.id)}
              >
                {item.title}
              </Button>
            ))}
          </div>
        ) : null}
        {!conversationId ? (
          <p className="mt-6 rounded-md bg-muted p-4 text-sm text-muted-foreground">
            Start a conversation after at least one source is ready.
          </p>
        ) : null}
        {conversation.data ? (
          <div className="mt-6 space-y-4">
            {conversation.data.messages.map((message) => (
              <article
                key={message.id}
                className={
                  message.role === "user"
                    ? "ml-8 rounded-md bg-primary p-3 text-primary-foreground"
                    : "mr-8 rounded-md bg-muted p-3"
                }
              >
                <p className="whitespace-pre-wrap text-sm">{message.content}</p>
                {message.citations.length ? (
                  <ul className="mt-3 space-y-2 border-t pt-3 text-xs">
                    {message.citations.map((citation) => (
                      <li key={`${message.id}-${citation.ordinal}`}>
                        <span className="font-medium">
                          {citation.source_display_name}
                          {citation.page_number ? ` · p. ${citation.page_number}` : ""}
                        </span>
                        <span className="text-muted-foreground"> — {citation.quote}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ))}
            {isStreaming ? (
              <article className="mr-8 rounded-md bg-muted p-3 text-sm">
                {streamingAnswer || "Thinking…"}
              </article>
            ) : null}
            <div className="flex gap-2">
              <input
                className="flex h-10 w-full rounded-md border bg-background px-3 text-sm"
                disabled={isStreaming}
                placeholder="Ask about your sources…"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void sendQuestion()
                }}
              />
              <Button
                size="icon"
                disabled={isStreaming || !question.trim()}
                aria-label="Send question"
                onClick={() => void sendQuestion()}
              >
                <Send className="size-4" />
              </Button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  )
}
