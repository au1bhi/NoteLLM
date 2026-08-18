import { zodResolver } from "@hookform/resolvers/zod"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
  useNavigate,
} from "@tanstack/react-router"
import { MailCheck } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

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
import { useResendEmail } from "@/hooks/useResendEmail"

const PENDING_VERIFY_KEY = "pending-verify-email"

const formSchema = z
  .object({
    email: z.email({ message: "邮箱地址无效" }),
    full_name: z.string().min(1, { message: "请输入姓名" }),
    password: z
      .string()
      .min(1, { message: "请输入密码" })
      .min(8, { message: "密码至少需要 8 个字符" }),
    confirm_password: z.string().min(1, { message: "请确认密码" }),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "两次输入的密码不一致",
    path: ["confirm_password"],
  })

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/signup")({
  component: SignUp,
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
        title: "注册 - NoteLLM",
      },
    ],
  }),
})

function SignUp() {
  const { signUpMutation } = useAuth()
  const turnstile = useTurnstile()
  const navigate = useNavigate()
  // A just-registered address is remembered in this tab, so refreshing or
  // going back after signup keeps the "check your inbox" screen instead of
  // dropping the user back into the form (where re-submitting would fail with
  // "该邮箱已存在").
  const [registered, setRegistered] = useState<{ email: string } | null>(() => {
    const pending = sessionStorage.getItem(PENDING_VERIFY_KEY)
    return pending ? { email: pending } : null
  })
  const { resend, isPending, cooldown, disabled } = useResendEmail(
    registered?.email,
  )

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      email: "",
      full_name: "",
      password: "",
      confirm_password: "",
    },
  })

  const onSubmit = (data: FormData) => {
    if (signUpMutation.isPending) return

    // exclude confirm_password from submission data
    const { confirm_password: _confirm_password, ...submitData } = data
    signUpMutation.mutate(
      { ...submitData, turnstileToken: turnstile.token ?? undefined },
      {
        onSuccess: (created) => {
          if (created.is_email_verified) {
            // Mail backend not configured — account is already usable.
            sessionStorage.removeItem(PENDING_VERIFY_KEY)
            navigate({ to: "/login" })
          } else {
            sessionStorage.setItem(PENDING_VERIFY_KEY, created.email)
            setRegistered({ email: created.email })
          }
        },
        onError: turnstile.reset,
      },
    )
  }

  if (registered) {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center gap-6 text-center">
          <span className="inline-flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <MailCheck aria-hidden="true" className="size-6" />
          </span>
          <div className="space-y-1.5">
            <h1 className="text-2xl font-bold tracking-tight">
              验证邮件已发送
            </h1>
            <p className="text-sm text-muted-foreground">
              我们已向 {registered.email}{" "}
              提交发送了一封验证邮件，请点击邮件中的链接完成验证。
            </p>
          </div>
          <div className="grid w-full gap-3">
            <LoadingButton
              className="w-full"
              onClick={resend}
              loading={isPending}
              disabled={disabled && !isPending}
            >
              {isPending
                ? "发送中…"
                : cooldown > 0
                  ? `${cooldown}s 后可重发`
                  : "重新发送验证邮件"}
            </LoadingButton>
            <RouterLink to="/login">
              <LoadingButton
                variant="outline"
                className="w-full"
                loading={false}
              >
                稍后验证，先去登录
              </LoadingButton>
            </RouterLink>
          </div>
          <p className="text-xs text-muted-foreground">
            验证链接在 72 小时内有效。如果几分钟内未收到，请检查垃圾邮件文件夹。
          </p>
        </div>
      </AuthLayout>
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
            <h1 className="text-2xl font-bold tracking-tight">创建账户</h1>
            <p className="text-sm text-muted-foreground">
              开始整理你的学习与研究资料
            </p>
          </div>

          <div className="grid gap-4">
            <FormField
              control={form.control}
              name="full_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>姓名</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="full-name-input"
                      placeholder="姓名"
                      type="text"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>邮箱</FormLabel>
                  <FormControl>
                    <Input
                      data-testid="email-input"
                      placeholder="user@163.com"
                      type="email"
                      {...field}
                    />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">
                    仅支持常见邮箱域名（如 163.com、qq.com、gmail.com）。
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>密码</FormLabel>
                  <FormControl>
                    <PasswordInput
                      data-testid="password-input"
                      placeholder="密码"
                      {...field}
                    />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">
                    至少 8 个字符，建议混合字母与数字。
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="confirm_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>确认密码</FormLabel>
                  <FormControl>
                    <PasswordInput
                      data-testid="confirm-password-input"
                      placeholder="确认密码"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
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
              className="w-full"
              loading={signUpMutation.isPending}
              disabled={!turnstile.canSubmit}
            >
              注册
            </LoadingButton>
          </div>

          <div className="text-center text-sm">
            已有账户？{" "}
            <RouterLink to="/login" className="underline underline-offset-4">
              登录
            </RouterLink>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}
