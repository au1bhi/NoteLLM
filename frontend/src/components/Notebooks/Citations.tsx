import { ChevronDown, Link2 } from "lucide-react"
import { useState } from "react"

import type { CitationPublic } from "@/client"
import { cn } from "@/lib/utils"

interface CitationsProps {
  citations: CitationPublic[]
}

export function Citations({ citations }: CitationsProps) {
  const [listOpen, setListOpen] = useState(false)
  const [openOrdinals, setOpenOrdinals] = useState<Set<number>>(new Set())
  const [fullOrdinals, setFullOrdinals] = useState<Set<number>>(new Set())

  if (citations.length === 0) return null

  const toggleQuote = (ordinal: number) => {
    setOpenOrdinals((prev) => {
      const next = new Set(prev)
      if (next.has(ordinal)) next.delete(ordinal)
      else next.add(ordinal)
      return next
    })
  }

  const toggleFullChunk = (ordinal: number) => {
    setFullOrdinals((prev) => {
      const next = new Set(prev)
      if (next.has(ordinal)) next.delete(ordinal)
      else next.add(ordinal)
      return next
    })
  }

  return (
    <div className="mt-3 border-t pt-2.5">
      <button
        type="button"
        onClick={() => setListOpen((open) => !open)}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        aria-expanded={listOpen}
      >
        <Link2 className="size-3.5" />
        引用来源 ({citations.length})
        <ChevronDown
          className={cn(
            "size-3.5 transition-transform",
            listOpen && "rotate-180",
          )}
        />
      </button>

      {listOpen ? (
        <ul className="mt-2 space-y-1">
          {citations.map((citation) => {
            const isOpen = openOrdinals.has(citation.ordinal)
            return (
              <li key={`${citation.chunk_id}-${citation.ordinal}`}>
                <button
                  type="button"
                  onClick={() => toggleQuote(citation.ordinal)}
                  className="group flex w-full items-baseline gap-2 rounded-md px-1 py-0.5 text-left text-xs transition-colors hover:bg-muted/50"
                  aria-expanded={isOpen}
                >
                  <span className="inline-flex size-4 shrink-0 translate-y-[2px] items-center justify-center rounded-full bg-primary text-[9px] font-semibold text-white">
                    {citation.ordinal}
                  </span>
                  <span className="min-w-0">
                    <span className="font-medium text-primary group-hover:underline">
                      {citation.source_display_name}
                    </span>
                    {citation.page_number != null ? (
                      <span className="text-muted-foreground">
                        {" "}
                        · 第 {citation.page_number} 页
                      </span>
                    ) : null}
                  </span>
                  <ChevronDown
                    className={cn(
                      "ml-auto size-3 shrink-0 text-muted-foreground transition-transform",
                      isOpen && "rotate-180",
                    )}
                  />
                </button>
                {isOpen ? (
                  <div className="mt-1 space-y-2">
                    <p className="whitespace-pre-wrap rounded-lg border bg-muted/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                      “{citation.quote}”
                    </p>
                    {citation.chunk_content ? (
                      <div className="space-y-2">
                        <button
                          type="button"
                          className="text-xs font-medium text-primary hover:underline"
                          aria-expanded={fullOrdinals.has(citation.ordinal)}
                          onClick={() => toggleFullChunk(citation.ordinal)}
                        >
                          {fullOrdinals.has(citation.ordinal)
                            ? "收起完整引用片段"
                            : "查看完整引用片段"}
                        </button>
                        {fullOrdinals.has(citation.ordinal) ? (
                          <>
                            <p className="text-xs text-muted-foreground">
                              当前资料块，非完整文件或永久归档；资料更改或删除后可能变化。
                            </p>
                            <div className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg border bg-muted/40 px-3 py-2 text-xs leading-relaxed text-foreground">
                              {citation.chunk_content}
                            </div>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}
