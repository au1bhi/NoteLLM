import { Link } from "@tanstack/react-router"
import { ArrowLeft } from "lucide-react"

import { Logo } from "@/components/Common/Logo"
import { Button } from "@/components/ui/button"

const NotFound = () => {
  return (
    <div
      className="flex min-h-svh flex-col items-center justify-center gap-8 p-4"
      data-testid="not-found"
    >
      <Logo variant="full" asLink={false} />
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="text-gradient text-7xl font-bold leading-none">
          404
        </span>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">页面不存在</h1>
        <p className="max-w-sm text-muted-foreground">
          你访问的页面可能已被移动或删除。
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

export default NotFound
