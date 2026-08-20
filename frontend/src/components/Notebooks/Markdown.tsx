import "katex/dist/katex.min.css"

import { useMemo } from "react"
import type { Components } from "react-markdown"
import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"

interface MarkdownProps {
  content: string
}

function safeUrlTransform(url: string): string {
  const transformed = defaultUrlTransform(url)
  if (!transformed) return ""
  const lower = transformed.trim().toLowerCase()
  if (lower.startsWith("https:") || lower.startsWith("http:")) {
    return transformed
  }
  // Drop javascript:, data:, mailto: and any other unexpected protocol so a
  // model-generated answer cannot become a phishing or script vector.
  return ""
}

/**
 * Normalizes alternative LaTeX delimiters often emitted by LLMs
 * \( ... \) -> $ ... $
 * \[ ... \] -> $$ ... $$
 */
function normalizeMathDelimiters(markdown: string): string {
  if (!markdown) return ""
  return markdown
    .replace(
      /\\\[([\s\S]*?)\\\]/g,
      (_, formula) => `\n$$\n${formula.trim()}\n$$\n`,
    )
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, formula) => `$${formula.trim()}$`)
}

const markdownComponents: Components = {
  a: ({ href, children, ...props }) => (
    <a {...props} href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
}

export function Markdown({ content }: MarkdownProps) {
  const processedContent = useMemo(
    () => normalizeMathDelimiters(content),
    [content],
  )

  return (
    <div className="markdown prose prose-sm max-w-none prose-neutral dark:prose-invert prose-headings:tracking-tight prose-p:leading-relaxed prose-math:overflow-x-auto">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        urlTransform={safeUrlTransform}
        components={markdownComponents}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  )
}
