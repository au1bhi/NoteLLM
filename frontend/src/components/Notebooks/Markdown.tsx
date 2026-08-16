import type { Components } from "react-markdown"
import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import remarkGfm from "remark-gfm"

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

const markdownComponents: Components = {
  a: ({ href, children, ...props }) => (
    <a {...props} href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
}

export function Markdown({ content }: MarkdownProps) {
  return (
    <div className="markdown prose prose-sm max-w-none prose-neutral dark:prose-invert prose-headings:tracking-tight prose-p:leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={safeUrlTransform}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
