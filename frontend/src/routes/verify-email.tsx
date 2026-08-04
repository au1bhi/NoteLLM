import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createFileRoute,
  Link as RouterLink,
  useNavigate,
} from "@tanstack/react-router"
import { Loader2, MailCheck, MailWarning, RefreshCw } from "lucide-react"
import { useEffect } from "react"

import { ApiError, UsersService } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import { Button } from "@/components/ui/button"
import { isLoggedIn } from "@/hooks/useAuth"
import { consumeTokenFromHash } from "@/lib/auth"

// The verify JWT is delivered in the URL *fragment* (`#token=...`), never the
// query string, so it is not written to proxy access logs and is not leaked
// through the Referer header. `consumeTokenFromHash` reads it and immediately
// strips the fragment from the address bar and history, so the token does not
// linger in history for its 72h validity window.

export const Route = createFileRoute("/verify-email")({
  component: VerifyEmail,
  beforeLoad: (): { token: string } => {
    return { token: consumeTokenFromHash() }
  },
  head: () => ({
    meta: [
      {
        title: "验证邮箱 - NoteLLM",
      },
    ],
  }),
})

function VerifyEmail() {
  const { token } = Route.useRouteContext()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { isLoading, isSuccess, error, refetch } = useQuery({
    queryKey: ["verify-email", token],
    queryFn: () => UsersService.verifyEmail({ requestBody: { token } }),
    enabled: !!token,
    retry: false,
  })

  useEffect(() => {
    // If the recipient is already logged in (e.g. opened the link in another
    // tab), refresh the profile so the reminder banner disappears.
    if (isSuccess) {
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
    }
  }, [isSuccess, queryClient])

  const invalidToken = error instanceof ApiError && error.status === 400

  return (
    <AuthLayout>
      <div className="flex flex-col items-center gap-6 text-center">
        {!token ? (
          <>
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <MailWarning aria-hidden="true" className="size-6" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight">验证链接无效</h1>
            <p className="text-sm text-muted-foreground">
              邮件中的链接不完整。请返回应用重新发送验证邮件。
            </p>
            <RouterLink to="/login">
              <Button variant="outline" className="w-full">
                返回登录
              </Button>
            </RouterLink>
          </>
        ) : isLoading ? (
          <>
            <Loader2
              aria-hidden="true"
              className="size-10 animate-spin text-primary"
            />
            <h1 className="text-2xl font-bold tracking-tight">正在验证邮箱</h1>
            <p className="text-sm text-muted-foreground">请稍候…</p>
          </>
        ) : isSuccess ? (
          <>
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <MailCheck aria-hidden="true" className="size-6" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight">邮箱验证成功</h1>
            <p className="text-sm text-muted-foreground">
              你的邮箱已确认，现在可以正常使用所有功能了。
            </p>
            {isLoggedIn() ? (
              <Button className="w-full" onClick={() => navigate({ to: "/" })}>
                进入应用
              </Button>
            ) : (
              <RouterLink to="/login">
                <Button className="w-full">去登录</Button>
              </RouterLink>
            )}
          </>
        ) : invalidToken ? (
          <>
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <MailWarning aria-hidden="true" className="size-6" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight">
              验证链接无效或已过期
            </h1>
            <p className="text-sm text-muted-foreground">
              请返回应用重新发送验证邮件，然后使用最新链接完成验证。
            </p>
            <RouterLink to="/login">
              <Button variant="outline" className="w-full">
                返回登录
              </Button>
            </RouterLink>
          </>
        ) : (
          <>
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <MailWarning aria-hidden="true" className="size-6" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight">
              验证服务暂时不可用
            </h1>
            <p className="text-sm text-muted-foreground">
              网络异常或服务器暂时繁忙，请稍后重试。
            </p>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => refetch()}
            >
              <RefreshCw aria-hidden="true" className="mr-2 size-4" />
              重试
            </Button>
          </>
        )}
      </div>
    </AuthLayout>
  )
}
