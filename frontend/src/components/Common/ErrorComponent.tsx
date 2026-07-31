import { Link } from "@tanstack/react-router"
import { ArrowLeft } from "lucide-react"

import { Logo } from "@/components/Common/Logo"
import { Button } from "@/components/ui/button"

const ErrorComponent = () => {
  return (
    <div
      className="flex min-h-svh flex-col items-center justify-center gap-8 p-4"
      data-testid="error-component"
    >
      <Logo variant="full" asLink={false} />
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="text-gradient text-6xl font-bold leading-none">
          Oops
        </span>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">出了点问题</h1>
        <p className="max-w-sm text-muted-foreground">
          发生了一些错误，请稍后重试。
        </p>
      </div>
      <Button asChild>
        <Link to="/">
          <ArrowLeft className="size-4" />
          返回首页
        </Link>
      </Button>
    </div>
  )
}

export default ErrorComponent
