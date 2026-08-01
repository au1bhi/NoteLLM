import {
  type CitationPublic,
  type ConversationDetailPublic,
  type ConversationPublic,
  ConversationsService,
  type ConversationUpdate,
  NotebooksService,
  OpenAPI,
} from "@/client"

type StreamHandlers = {
  onCitations: (citations: CitationPublic[]) => void
  onDelta: (text: string) => void
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
  ): Promise<void> => {
    const response = await fetch(
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
          Authorization: `Bearer ${localStorage.getItem("access_token") || ""}`,
          "Content-Type": "application/json",
        },
        method: "POST",
      },
    )
    if (!response.ok || !response.body) {
      throw new Error("无法启动回答流")
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let event = "message"

    const processLine = (line: string) => {
      if (line.startsWith("event: ")) event = line.slice(7)
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6)) as {
          citations?: CitationPublic[]
          message?: string
          text?: string
        }
        if (event === "delta" && data.text) handlers.onDelta(data.text)
        if (event === "citations" && data.citations) {
          handlers.onCitations(data.citations)
        }
        if (event === "error") throw new Error(data.message || "回答失败")
      }
    }

    const processRecord = (record: string) => {
      for (const line of record.split("\n")) processLine(line)
    }

    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      buffer = buffer.replace(/\r\n/g, "\n")
      const records = buffer.split("\n\n")
      buffer = records.pop() || ""
      for (const record of records) {
        processRecord(record)
      }
      if (done) {
        if (buffer.trim()) processRecord(buffer)
        return
      }
    }
  },
}

export type Conversation = ConversationPublic
export type ConversationDetail = ConversationDetailPublic
