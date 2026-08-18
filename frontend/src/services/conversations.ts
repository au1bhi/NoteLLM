import {
  type CitationPublic,
  type ConversationDetailPublic,
  type ConversationPublic,
  ConversationsService,
  type ConversationUpdate,
  NotebooksService,
  OpenAPI,
} from "@/client"
import { AUTH_EXPIRED_KEY, clearToken, getToken } from "@/lib/auth"

type StreamHandlers = {
  onCitations: (citations: CitationPublic[]) => void
  onDelta: (text: string) => void
  onDone?: () => void
  onPhase?: (phase: "retrieving" | "generating" | "saving") => void
  mode?: AnswerMode
  sourceIds?: string[]
}

export type AnswerMode = "grounded" | "hybrid" | "knowledge"

export const conversationsApi = {
  create: (notebookId: string) =>
    NotebooksService.createConversation({
      notebookId,
      requestBody: {},
    }),
  get: (conversationId: string) =>
    ConversationsService.readConversation({ conversationId }),
  list: (notebookId: string) =>
    NotebooksService.readConversations({ notebookId }),
  update: (conversationId: string, input: ConversationUpdate) =>
    ConversationsService.updateConversation({
      conversationId,
      requestBody: input,
    }),
  delete: (conversationId: string) =>
    ConversationsService.deleteConversation({ conversationId }),
  stream: async (
    conversationId: string,
    content: string,
    handlers: StreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> => {
    let response: Response
    try {
      response = await fetch(
        `${OpenAPI.BASE}/api/v1/conversations/${conversationId}/messages/stream`,
        {
          body: JSON.stringify({
            content,
            mode: handlers.mode ?? "grounded",
            source_ids: handlers.sourceIds?.length
              ? handlers.sourceIds
              : undefined,
          }),
          headers: {
            Authorization: `Bearer ${getToken() ?? ""}`,
            "Content-Type": "application/json",
          },
          method: "POST",
          signal,
        },
      )
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error
      }
      throw new Error("网络连接失败，无法接收回答")
    }
    // Streaming requests bypass the generated client, so a 401 here never
    // reached the QueryClient error handler. Treat it like every other stale
    // session: drop the token and land on the login page immediately.
    if (response.status === 401 || response.status === 403) {
      clearToken()
      sessionStorage.setItem(AUTH_EXPIRED_KEY, "1")
      window.location.href = "/login"
      throw new Error("登录已过期，请重新登录")
    }
    if (!response.ok) {
      let detail = "无法启动回答流"
      try {
        const body = (await response.json()) as { detail?: unknown }
        if (typeof body.detail === "string" && body.detail) detail = body.detail
        else if (Array.isArray(body.detail) && body.detail.length > 0) {
          const first = body.detail[0] as { msg?: unknown }
          if (typeof first.msg === "string" && first.msg) detail = first.msg
        }
      } catch {
        // Keep the safe fallback for non-JSON proxy responses.
      }
      throw new Error(detail)
    }
    if (!response.body) {
      throw new Error("回答流不可用，请稍后重试")
    }

    handlers.onPhase?.(
      handlers.mode === "knowledge" ? "generating" : "retrieving",
    )
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let completed = false

    const cancelReader = async () => {
      try {
        await reader.cancel()
      } catch {
        // The transport may already be closed after the terminal SSE event.
      }
    }

    const processRecord = (record: string) => {
      let event = "message"
      const lines = record.split("\n")
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          event = line.slice(7)
          continue
        }
        if (!line.startsWith("data: ")) continue
        let data: {
          citations?: CitationPublic[]
          message?: string
          text?: string
        }
        try {
          data = JSON.parse(line.slice(6)) as typeof data
        } catch {
          throw new Error("回答流格式无效，请重试")
        }
        if (event === "delta" && data.text) {
          handlers.onPhase?.("generating")
          handlers.onDelta(data.text)
        }
        if (event === "citations" && data.citations) {
          handlers.onPhase?.("saving")
          handlers.onCitations(data.citations)
        }
        if (event === "done") {
          completed = true
          handlers.onDone?.()
        }
        if (event === "error") throw new Error(data.message || "回答失败")
      }
    }

    while (true) {
      let result: ReadableStreamReadResult<Uint8Array>
      try {
        result = await reader.read()
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          throw error
        }
        throw new Error("回答连接已中断，请重试")
      }
      const { done, value } = result
      buffer += decoder.decode(value, { stream: !done })
      buffer = buffer.replace(/\r\n/g, "\n")
      const records = buffer.split("\n\n")
      buffer = records.pop() || ""
      for (const record of records) {
        try {
          processRecord(record)
        } catch (error) {
          await cancelReader()
          throw error
        }
        if (completed) {
          await cancelReader()
          return
        }
      }
      if (done) {
        if (buffer.trim()) {
          try {
            processRecord(buffer)
          } catch (error) {
            await cancelReader()
            throw error
          }
        }
        if (completed) {
          await cancelReader()
          return
        }
        throw new Error("回答流意外结束，请重试")
      }
    }
  },
}

export type Conversation = ConversationPublic
export type ConversationDetail = ConversationDetailPublic
