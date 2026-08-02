import { useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link as RouterLink } from "@tanstack/react-router"
import { Loader2, MailCheck, MailWarning } from "lucide-react"
import { useEffect } from "react"
import { z } from "zod"

import { UsersService } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import { Button } from "@/components/ui/button"

const searchSchema = z.object({
  token: z.string().catch(""),
})

export const Route = createFileRoute("/verify-email")({
  component: VerifyEmail,
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      {
        title: "验证邮箱 - NoteLLM",
      },
    ],
  }),
})

function VerifyEmail() {
  const { token } = Route.useSearch()
  const queryClient = useQueryClient()

  const { isLoading, isSuccess } = useQuery({
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

  return (
    <AuthLayout>
      <div className="flex flex-col items-center gap-6 text-center">
        {!token ? (
          <>
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <MailWarning className="size-6" />
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
            <Loader2 className="size-10 animate-spin text-primary" />
            <h1 className="text-2xl font-bold tracking-tight">正在验证邮箱</h1>
            <p className="text-sm text-muted-foreground">请稍候…</p>
          </>
        ) : isSuccess ? (
          <>
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <MailCheck className="size-6" />
            </span>
            <h1 className="text-2xl font-bold tracking-tight">邮箱验证成功</h1>
            <p className="text-sm text-muted-foreground">
              你的邮箱已确认，现在可以正常使用所有功能了。
            </p>
            <RouterLink to="/login">
              <Button className="w-full">去登录</Button>
            </RouterLink>
          </>
        ) : (
          <>
            <span className="inline-flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <MailWarning className="size-6" />
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
        )}
      </div>
    </AuthLayout>
  )
}
