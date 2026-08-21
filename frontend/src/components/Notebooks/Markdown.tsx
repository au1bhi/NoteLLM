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
 * Robust normalizer for LaTeX delimiters across all LLM output styles:
 * 1. \[ ... \] -> $$ ... $$
 * 2. \( ... \) -> $ ... $
 * 3. \begin{equation|align|aligned|gather|matrix|pmatrix|bmatrix|cases}...\end{...} -> $$ \begin{...}...\end{...} $$
 * 4. Fixes `$ math $` with unwanted whitespace adjacent to dollar signs so remark-math parses inline math correctly
 */
function normalizeMathDelimiters(markdown: string): string {
  if (!markdown) return ""
  return (
    markdown
      // Convert \[ ... \] to display math block
      .replace(
        /\\\[([\s\S]*?)\\\]/g,
        (_, formula) => `\n$$\n${formula.trim()}\n$$\n`,
      )
      // Convert \( ... \) to inline math
      .replace(/\\\(([\s\S]*?)\\\)/g, (_, formula) => `$${formula.trim()}$`)
      // Wrap bare LaTeX environments in display math
      .replace(
        /(?<!\$)\s*(\\begin\{(?:equation|align|aligned|gather|matrix|pmatrix|bmatrix|vmatrix|cases)\*?\}[\s\S]*?\\end\{(?:equation|align|aligned|gather|matrix|pmatrix|bmatrix|vmatrix|cases)\*?\})\s*(?!\$)/g,
        (_, env) => `\n$$\n${env.trim()}\n$$\n`,
      )
      // Trim spaces directly inside $...$ so remark-math parses them as math
      .replace(
        /(?<=^|[^\\$])\$\s+([^$\n]+?)\s+\$(?=[^$]|$)/g,
        (_, formula) => `$${formula.trim()}$`,
      )
      .replace(
        /(?<=^|[^\\$])\$\s+([^$\n]+?)\$(?=[^$]|$)/g,
        (_, formula) => `$${formula.trim()}$`,
      )
      .replace(
        /(?<=^|[^\\$])\$([^$\n]+?)\s+\$(?=[^$]|$)/g,
        (_, formula) => `$${formula.trim()}$`,
      )
  )
}

const rehypeKatexOptions = {
  throwOnError: false,
  errorColor: "#ef4444",
  strict: false,
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
        rehypePlugins={[[rehypeKatex, rehypeKatexOptions]]}
        urlTransform={safeUrlTransform}
        components={markdownComponents}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  )
}
