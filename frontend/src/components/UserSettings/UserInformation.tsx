import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { ApiError, UsersService, type UserUpdateMe } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { useResendEmail } from "@/hooks/useResendEmail"
import { cn } from "@/lib/utils"
import { handleError } from "@/utils"

const formSchema = z.object({
  full_name: z.string().max(30).optional(),
  email: z.email({ message: "邮箱地址无效" }),
  // Only required when the email is being changed (checked at submit time).
  current_password: z.string().optional(),
})

type FormData = z.infer<typeof formSchema>

const UserInformation = () => {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [editMode, setEditMode] = useState(false)
  const { user: currentUser } = useAuth()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      full_name: currentUser?.full_name ?? undefined,
      email: currentUser?.email,
      current_password: "",
    },
  })

  const toggleEditMode = () => {
    setEditMode(!editMode)
  }

  const mutation = useMutation({
    mutationFn: (data: UserUpdateMe) =>
      UsersService.updateUserMe({ requestBody: data }),
    onSuccess: () => {
      showSuccessToast("个人信息已更新")
      toggleEditMode()
    },
    onError: (error: Error) => {
      // A rejected password while changing the email belongs on the field, not
      // just in a toast.
      if (error instanceof ApiError) {
        const detail = (error.body as { detail?: string } | undefined)?.detail
        if (error.status === 400 && detail === "当前密码错误") {
          form.setError("current_password", { message: "当前密码错误" })
          return
        }
        handleError.call(showErrorToast, error)
        return
      }
      showErrorToast("操作失败，请稍后重试")
    },
    onSettled: () => {
      queryClient.invalidateQueries()
    },
  })

  const { resend, isPending: resending, cooldown, disabled } = useResendEmail()

  const typedEmail = form.watch("email")
  const emailChanged = editMode && typedEmail !== currentUser?.email

  const onSubmit = (data: FormData) => {
    const updateData: UserUpdateMe = {}

    // only include fields that have changed
    if (data.full_name !== currentUser?.full_name) {
      updateData.full_name = data.full_name
    }
    if (data.email !== currentUser?.email) {
      if (!data.current_password) {
        form.setError("current_password", {
          message: "修改邮箱需要验证当前密码",
        })
        return
      }
      updateData.email = data.email
      updateData.current_password = data.current_password
    }

    mutation.mutate(updateData)
  }

  const onCancel = () => {
    form.reset()
    toggleEditMode()
  }

  return (
    <div className="max-w-md">
      <h3 className="text-lg font-semibold py-4">个人信息</h3>
      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-4"
        >
          <FormField
            control={form.control}
            name="full_name"
            render={({ field }) =>
              editMode ? (
                <FormItem>
                  <FormLabel>姓名</FormLabel>
                  <FormControl>
                    <Input type="text" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              ) : (
                <FormItem>
                  <FormLabel>姓名</FormLabel>
                  <p
                    className={cn(
                      "py-2 truncate max-w-sm",
                      !field.value && "text-muted-foreground",
                    )}
                  >
                    {field.value || "未设置"}
                  </p>
                </FormItem>
              )
            }
          />

          <FormField
            control={form.control}
            name="email"
            render={({ field }) =>
              editMode ? (
                <FormItem>
                  <FormLabel>邮箱</FormLabel>
                  <FormControl>
                    <Input type="email" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              ) : (
                <FormItem>
                  <FormLabel>邮箱</FormLabel>
                  <div className="flex items-center gap-2 py-2">
                    <p className="truncate max-w-sm">{field.value}</p>
                    {currentUser?.is_email_verified ? (
                      <Badge>已验证</Badge>
                    ) : (
                      <>
                        <Badge variant="secondary">未验证</Badge>
                        <Button
                          type="button"
                          variant="link"
                          size="sm"
                          className="px-1 text-primary"
                          onClick={resend}
                          disabled={disabled}
                        >
                          {resending
                            ? "发送中…"
                            : cooldown > 0
                              ? `${cooldown}s 后可重发`
                              : "发送验证邮件"}
                        </Button>
                      </>
                    )}
                  </div>
                </FormItem>
              )
            }
          />

          {editMode && emailChanged && (
            <FormField
              control={form.control}
              name="current_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>当前密码</FormLabel>
                  <FormControl>
                    <PasswordInput
                      autoComplete="current-password"
                      placeholder="输入当前密码以确认修改邮箱"
                      {...field}
                    />
                  </FormControl>
                  <p className="text-xs text-muted-foreground">
                    修改邮箱后需重新验证新邮箱。
                  </p>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          <div className="flex gap-3">
            {editMode ? (
              <>
                <LoadingButton
                  type="submit"
                  loading={mutation.isPending}
                  disabled={!form.formState.isDirty}
                >
                  保存
                </LoadingButton>
                <Button
                  type="button"
                  variant="outline"
                  onClick={onCancel}
                  disabled={mutation.isPending}
                >
                  取消
                </Button>
              </>
            ) : (
              <Button type="button" onClick={toggleEditMode}>
                编辑
              </Button>
            )}
          </div>
        </form>
      </Form>
    </div>
  )
}

export default UserInformation
