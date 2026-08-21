import "katex/dist/katex.min.css"

import { Check, Copy } from "lucide-react"
import { useMemo, useState } from "react"
import type { Components } from "react-markdown"
import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"

import { cn } from "@/lib/utils"

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

function CodeBlock({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLElement> & { className?: string }) {
  const match = /language-(\w+)/.exec(className || "")
  const isInline = !match && !String(children).includes("\n")
  const [copied, setCopied] = useState(false)

  if (isInline) {
    return (
      <code
        className={cn(
          "rounded bg-muted px-1.5 py-0.5 text-[0.875em] font-mono font-medium text-foreground",
          className,
        )}
        {...props}
      >
        {children}
      </code>
    )
  }

  const codeText = String(children).replace(/\n$/, "")
  const handleCopy = () => {
    void navigator.clipboard.writeText(codeText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="group relative my-3 overflow-hidden rounded-xl border bg-muted/40 text-foreground dark:bg-muted/20">
      <div className="flex items-center justify-between border-b bg-muted/60 px-3.5 py-1 text-xs text-muted-foreground">
        <span className="font-mono text-[11px] font-semibold uppercase tracking-wider">
          {match ? match[1] : "code"}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
        >
          {copied ? (
            <Check className="size-3 text-primary" />
          ) : (
            <Copy className="size-3" />
          )}
          <span>{copied ? "已复制" : "复制"}</span>
        </button>
      </div>
      <pre className="overflow-x-auto p-3.5 text-xs leading-relaxed font-mono">
        <code className={className} {...props}>
          {children}
        </code>
      </pre>
    </div>
  )
}

const markdownComponents: Components = {
  a: ({ href, children, ...props }) => (
    <a {...props} href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  code: CodeBlock,
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
