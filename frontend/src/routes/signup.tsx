import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
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

import { UsersService } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
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
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

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
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const navigate = useNavigate()
  const [registered, setRegistered] = useState<{ email: string } | null>(null)
  const [emailSent, setEmailSent] = useState(false)

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

  const resendMutation = useMutation({
    mutationFn: (email: string) =>
      UsersService.resendVerification({ requestBody: { email } }),
    onSuccess: () => {
      showSuccessToast("验证邮件已重新发送")
      setEmailSent(true)
    },
    onError: handleError.bind(showErrorToast),
  })

  const handleResend = () => {
    if (!registered || resendMutation.isPending) return
    resendMutation.mutate(registered.email)
  }

  const onSubmit = (data: FormData) => {
    if (signUpMutation.isPending) return

    // exclude confirm_password from submission data
    const { confirm_password: _confirm_password, ...submitData } = data
    signUpMutation.mutate(submitData, {
      onSuccess: (created) => {
        if (created.is_email_verified) {
          // Mail backend not configured — account is already usable.
          navigate({ to: "/login" })
        } else {
          setRegistered({ email: created.email })
          setEmailSent(false)
        }
      },
    })
  }

  if (registered) {
    return (
      <AuthLayout>
        <div className="flex flex-col items-center gap-6 text-center">
          <span className="inline-flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <MailCheck className="size-6" />
          </span>
          <div className="space-y-1.5">
            <h1 className="text-2xl font-bold tracking-tight">
              验证邮件已发送
            </h1>
            <p className="text-sm text-muted-foreground">
              我们已向 {registered.email}{" "}
              发送了一封验证邮件，请点击邮件中的链接完成验证。
            </p>
          </div>
          <div className="grid w-full gap-3">
            <LoadingButton
              className="w-full"
              onClick={handleResend}
              loading={resendMutation.isPending}
            >
              {emailSent ? "已重新发送" : "重新发送验证邮件"}
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
            验证链接在 72 小时内有效。如果找不到邮件，请检查垃圾邮件文件夹。
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
                      placeholder="user@example.com"
                      type="email"
                      {...field}
                    />
                  </FormControl>
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

            <LoadingButton
              type="submit"
              className="w-full"
              loading={signUpMutation.isPending}
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
