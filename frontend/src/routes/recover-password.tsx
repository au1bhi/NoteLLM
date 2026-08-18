import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation } from "@tanstack/react-query"
import {
  createFileRoute,
  Link as RouterLink,
  redirect,
} from "@tanstack/react-router"
import { useRef } from "react"
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
import { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { authApi } from "@/services/auth"
import { handleError } from "@/utils"

const formSchema = z.object({
  email: z.email({ message: "邮箱地址无效" }),
})

type FormData = z.infer<typeof formSchema>

export const Route = createFileRoute("/recover-password")({
  component: RecoverPassword,
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
        title: "找回密码 - NoteLLM",
      },
    ],
  }),
})

function RecoverPassword() {
  const turnstile = useTurnstile()
  const submitLock = useRef(false)
  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      email: "",
    },
  })
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const recoverPassword = async (data: FormData) => {
    await authApi.recoverPassword(data.email, turnstile.token ?? undefined)
  }

  const mutation = useMutation({
    mutationFn: recoverPassword,
    onSuccess: () => {
      showSuccessToast("密码找回邮件已发送")
      form.reset()
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      submitLock.current = false
      turnstile.reset()
    },
  })

  const onSubmit = async (data: FormData) => {
    if (submitLock.current || mutation.isPending) return
    submitLock.current = true
    mutation.mutate(data)
  }

  return (
    <AuthLayout>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-6"
        >
          <div className="flex flex-col items-center gap-1.5 text-center">
            <h1 className="text-2xl font-bold tracking-tight">找回密码</h1>
            <p className="text-sm text-muted-foreground">
              输入注册邮箱，我们将发送重置链接
            </p>
          </div>

          <div className="grid gap-4">
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
              loading={mutation.isPending}
              disabled={!turnstile.canSubmit}
            >
              继续
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
