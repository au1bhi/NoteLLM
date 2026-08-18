import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
} from "@tanstack/react-router"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import type { Body_login_login_access_token as AccessToken } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import { Turnstile, useTurnstile } from "@/components/Common/Turnstile"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { PasswordInput } from "@/components/ui/password-input"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import { AUTH_EXPIRED_KEY } from "@/lib/auth"

const formSchema = z.object({
  username: z.email({ message: "邮箱地址无效" }),
  password: z
    .string()
    .min(1, { message: "请输入密码" })
    .min(8, { message: "密码至少需要 8 个字符" }),
}) satisfies z.ZodType<AccessToken>

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/login")({
  component: Login,
  beforeLoad: async () => {
    if (isLoggedIn()) {
      throw redirect({
        to: "/",
      })
    }
  },
  head: () => ({
    meta: [
      {
        title: "登录 - NoteLLM",
      },
    ],
  }),
})

function Login() {
  const { loginMutation } = useAuth()
  const turnstile = useTurnstile()
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      username: "",
      password: "",
    },
  })

  useEffect(() => {
    if (sessionStorage.getItem(AUTH_EXPIRED_KEY)) {
      sessionStorage.removeItem(AUTH_EXPIRED_KEY)
      toast.error("登录已过期，请重新登录", {
        description: "长时间未操作，为保障账户安全已退出登录。",
      })
    }
  }, [])

  const onSubmit = (data: FormData) => {
    if (loginMutation.isPending) return
    loginMutation.mutate(
      { ...data, turnstileToken: turnstile.token ?? undefined },
      { onError: turnstile.reset },
    )
  }

  return (
    <AuthLayout>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-6"
        >
          <div className="flex flex-col items-center gap-1.5 text-center">
            <h1 className="text-2xl font-bold tracking-tight">登录你的账户</h1>
            <p className="text-sm text-muted-foreground">欢迎回到 NoteLLM</p>
          </div>

          <div className="grid gap-4">
            <FormField
              control={form.control}
              name="username"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>邮箱</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="email-input"
                      placeholder="user@example.com"
                      type="email"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage className="text-xs" />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <div className="flex items-center">
                    <FormLabel>密码</FormLabel>
                    <RouterLink
                      to="/recover-password"
                      className="ml-auto text-sm underline-offset-4 hover:underline"
                    >
                      忘记密码？
                    </RouterLink>
                  </div>
                  <FormControl>
                    <PasswordInput
                      data-testid="password-input"
                      placeholder="密码"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage className="text-xs" />
                </FormItem>
              )}
            />

            <Turnstile
              enabled={turnstile.enabled}
              siteKey={turnstile.siteKey}
              resetKey={turnstile.resetKey}
              isLoading={turnstile.isLoading}
              isError={turnstile.isError}
              onTokenChange={turnstile.setToken}
              onRetryConfig={() => void turnstile.retryConfig()}
            />

            <LoadingButton
              type="submit"
              loading={loginMutation.isPending}
              disabled={!turnstile.canSubmit}
            >
              登录
            </LoadingButton>
          </div>

          <div className="text-center text-sm">
            还没有账户？{" "}
            <RouterLink to="/signup" className="underline underline-offset-4">
              注册
            </RouterLink>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}
