export function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="border-t px-6 py-5">
      <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-2 text-sm text-muted-foreground sm:flex-row">
        <p>NoteLLM — 面向个人学习与研究的文档问答</p>
        <p>© {currentYear} NoteLLM</p>
      </div>
    </footer>
  )
}
