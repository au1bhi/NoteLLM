import {
  type CitationPublic,
  type ConversationDetailPublic,
  type ConversationPublic,
  ConversationsService,
  NotebooksService,
  OpenAPI,
} from "@/client"

type StreamHandlers = {
  onCitations: (citations: CitationPublic[]) => void
  onDelta: (text: string) => void
}

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
  stream: async (
    conversationId: string,
    content: string,
    handlers: StreamHandlers,
  ): Promise<void> => {
    const response = await fetch(
      `${OpenAPI.BASE}/api/v1/conversations/${conversationId}/messages/stream`,
      {
        body: JSON.stringify({ content }),
        headers: {
          Authorization: `Bearer ${localStorage.getItem("access_token") || ""}`,
          "Content-Type": "application/json",
        },
        method: "POST",
      },
    )
    if (!response.ok || !response.body) {
      throw new Error("Unable to start the grounded answer stream")
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let event = "message"
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      buffer = buffer.replace(/\r\n/g, "\n")
      const records = buffer.split("\n\n")
      buffer = records.pop() || ""
      for (const record of records) {
        for (const line of record.split("\n")) {
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
            if (event === "error") throw new Error(data.message || "Answer failed")
          }
        }
      }
      if (done) return
    }
  },
}

export type Conversation = ConversationPublic
export type ConversationDetail = ConversationDetailPublic
