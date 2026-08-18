import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
  useNavigate,
} from "@tanstack/react-router"
import { useRef } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { LoginService } from "@/client"
import { AuthLayout } from "@/components/Common/AuthLayout"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import { PasswordInput } from "@/components/ui/password-input"
import { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { consumeTokenFromHash } from "@/lib/auth"
import { handleError } from "@/utils"

const formSchema = z
  .object({
    new_password: z
      .string()
      .min(1, { message: "请输入密码" })
      .min(8, { message: "密码至少需要 8 个字符" }),
    confirm_password: z.string().min(1, { message: "请确认密码" }),
  })
  .refine((data) => data.new_password === data.confirm_password, {
    message: "两次输入的密码不一致",
    path: ["confirm_password"],
  })

type FormData = z.infer<typeof formSchema>

// The reset JWT is delivered in the URL *fragment* (`#token=...`), never the
// query string, so it is not written to proxy access logs and is not leaked
// through the Referer header. `consumeTokenFromHash` reads it and immediately
// strips the fragment from the address bar and history, so an opened-but-unused
// link cannot be replayed from history for the token's 48h validity window.

export const Route = createFileRoute("/reset-password")({
  component: ResetPassword,
  beforeLoad: (): { token: string } => {
    if (isLoggedIn()) {
      throw redirect({ to: "/" })
    }
    // Consume the fragment token (stripping it from the URL) and thread it
    // through the route context so the form can submit it.
    const token = consumeTokenFromHash()
    if (!token) {
      throw redirect({ to: "/login" })
    }
    return { token }
  },
  head: () => ({
    meta: [
      {
        title: "重置密码 - NoteLLM",
      },
    ],
  }),
})

function ResetPassword() {
  const { token } = Route.useRouteContext()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const navigate = useNavigate()
  const submitLock = useRef(false)

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      new_password: "",
      confirm_password: "",
    },
  })

  const mutation = useMutation({
    mutationFn: (data: { new_password: string; token: string }) =>
      LoginService.resetPassword({ requestBody: data }),
    onSuccess: () => {
      showSuccessToast("密码已更新")
      form.reset()
      navigate({ to: "/login" })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      submitLock.current = false
    },
  })

  const onSubmit = (data: FormData) => {
    if (submitLock.current || mutation.isPending) return
    submitLock.current = true
    mutation.mutate({ new_password: data.new_password, token })
  }

  return (
    <AuthLayout>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-6"
        >
          <div className="flex flex-col items-center gap-1.5 text-center">
            <h1 className="text-2xl font-bold tracking-tight">重置密码</h1>
            <p className="text-sm text-muted-foreground">设置一个新密码</p>
          </div>

          <div className="grid gap-4">
            <FormField
              control={form.control}
              name="new_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>新密码</FormLabel>
                  <FormControl>
                    <PasswordInput
                      data-testid="new-password-input"
                      placeholder="新密码"
                      {...field}
                    />
                  </FormControl>
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
              loading={mutation.isPending}
            >
              重置密码
            </LoadingButton>
          </div>

          <div className="text-center text-sm">
            记得密码？{" "}
            <RouterLink to="/login" className="underline underline-offset-4">
              登录
            </RouterLink>
          </div>
        </form>
      </Form>
    </AuthLayout>
  )
}
