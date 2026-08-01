import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { KeyRound, RotateCcw } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { type Control, useForm } from "react-hook-form"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
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
import useCustomToast from "@/hooks/useCustomToast"
import { providerSettingsApi } from "@/services/provider-settings"
import { extractErrorMessage } from "@/utils"
import { ModelPicker } from "./ModelPicker"

const formSchema = z.object({
  chat_base_url: z.string().max(1000).optional().or(z.literal("")),
  chat_api_key: z.string().max(1000).optional().or(z.literal("")),
  chat_model: z.string().max(255).optional().or(z.literal("")),
  embedding_base_url: z.string().max(1000).optional().or(z.literal("")),
  embedding_api_key: z.string().max(1000).optional().or(z.literal("")),
  embedding_model: z.string().max(255).optional().or(z.literal("")),
})

type FormData = z.infer<typeof formSchema>

const EMPTY_FORM: FormData = {
  chat_base_url: "",
  chat_api_key: "",
  chat_model: "",
  embedding_base_url: "",
  embedding_api_key: "",
  embedding_model: "",
}

interface SectionConfig {
  title: string
  description: string
  baseUrl: keyof FormData
  apiKey: keyof FormData
  model: keyof FormData
  maskedKey: "chat_api_key" | "embedding_api_key"
}

const SECTIONS: SectionConfig[] = [
  {
    title: "对话模型",
    description: "用于生成带引用回答的模型（OpenAI 兼容接口）。",
    baseUrl: "chat_base_url",
    apiKey: "chat_api_key",
    model: "chat_model",
    maskedKey: "chat_api_key",
  },
  {
    title: "嵌入模型",
    description: "用于把资料向量化并检索的模型（OpenAI 兼容接口）。",
    baseUrl: "embedding_base_url",
    apiKey: "embedding_api_key",
    model: "embedding_model",
    maskedKey: "embedding_api_key",
  },
]

function SectionField({
  control,
  name,
  label,
  placeholder,
  type,
  masked,
}: {
  control: Control<FormData>
  name: keyof FormData
  label: string
  placeholder: string
  type?: "password"
  masked?: string
}) {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            {type === "password" ? (
              <PasswordInput
                placeholder={placeholder}
                autoComplete="off"
                {...field}
              />
            ) : (
              <Input placeholder={placeholder} {...field} />
            )}
          </FormControl>
          {masked ? (
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              <KeyRound className="size-3" />
              当前已设置：{masked}（留空则保持不变）
            </p>
          ) : null}
          <FormMessage />
        </FormItem>
      )}
    />
  )
}

export function ProviderSettings() {
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const queryClient = useQueryClient()
  const [clearOpen, setClearOpen] = useState(false)
  const hasLoadedRef = useRef(false)

  const { data } = useQuery({
    queryKey: ["provider-settings"],
    queryFn: providerSettingsApi.get,
  })

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: EMPTY_FORM,
  })

  useEffect(() => {
    // Only seed the form from the server once. Refetches after save/clear must
    // not wipe edits the user made while a mutation was in flight.
    if (!data || hasLoadedRef.current) return
    hasLoadedRef.current = true
    form.reset({
      chat_base_url: data.chat_base_url ?? "",
      chat_api_key: "",
      chat_model: data.chat_model ?? "",
      embedding_base_url: data.embedding_base_url ?? "",
      embedding_api_key: "",
      embedding_model: data.embedding_model ?? "",
    })
  }, [data, form])

  const saveMutation = useMutation({
    mutationFn: providerSettingsApi.update,
    onError: (error: Error) => showErrorToast(extractErrorMessage(error)),
    onSuccess: () => {
      showSuccessToast("模型配置已保存")
      queryClient.invalidateQueries({ queryKey: ["provider-settings"] })
    },
  })
  const clearMutation = useMutation({
    mutationFn: providerSettingsApi.clear,
    onError: (error: Error) => showErrorToast(extractErrorMessage(error)),
    onSuccess: () => {
      setClearOpen(false)
      form.reset(EMPTY_FORM)
      showSuccessToast("已清除，回退到服务端默认配置")
      queryClient.invalidateQueries({ queryKey: ["provider-settings"] })
    },
  })

  const onSubmit = (values: FormData) => {
    const trimmed: FormData = {}
    for (const [key, value] of Object.entries(values)) {
      trimmed[key as keyof FormData] =
        typeof value === "string" ? value.trim() : value
    }
    saveMutation.mutate(trimmed)
  }

  return (
    <div className="max-w-2xl">
      <div className="rounded-lg border border-primary/15 bg-primary/5 px-4 py-3 text-sm text-muted-foreground">
        在这里配置你自己的模型 API 密钥。留空的字段会回退到服务端默认配置；
        密钥只会加密保存在后端，前端永远看不到明文。
      </div>

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="mt-5 flex flex-col gap-6"
        >
          {SECTIONS.map((section) => (
            <section
              key={section.maskedKey}
              className="rounded-xl border bg-card p-5"
            >
              <h4 className="font-semibold tracking-tight">{section.title}</h4>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {section.description}
              </p>
              <div className="mt-4 grid gap-4">
                <SectionField
                  control={form.control}
                  name={section.baseUrl}
                  label="API Base URL"
                  placeholder="https://api.openai.com/v1"
                />
                <SectionField
                  control={form.control}
                  name={section.apiKey}
                  label="API Key"
                  placeholder="输入新的 API Key"
                  type="password"
                  masked={data?.[section.maskedKey] || undefined}
                />
                <FormField
                  control={form.control}
                  name={section.model}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>模型名</FormLabel>
                      <FormControl>
                        <ModelPicker
                          value={field.value ?? ""}
                          baseUrl={form.watch(section.baseUrl) ?? ""}
                          apiKey={form.watch(section.apiKey) ?? ""}
                          onValueChange={field.onChange}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </section>
          ))}

          <div className="flex flex-wrap items-center gap-3">
            <LoadingButton
              type="submit"
              loading={saveMutation.isPending}
              disabled={!form.formState.isDirty}
            >
              保存配置
            </LoadingButton>
            <Dialog open={clearOpen} onOpenChange={setClearOpen}>
              <DialogTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  disabled={clearMutation.isPending}
                >
                  <RotateCcw className="size-4" />
                  清除配置
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle>清除模型配置</DialogTitle>
                  <DialogDescription>
                    将删除你保存的 API 密钥与配置，之后使用服务端默认配置。
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <DialogClose asChild>
                    <Button
                      variant="outline"
                      disabled={clearMutation.isPending}
                    >
                      取消
                    </Button>
                  </DialogClose>
                  <LoadingButton
                    variant="destructive"
                    loading={clearMutation.isPending}
                    onClick={() => clearMutation.mutate()}
                  >
                    清除
                  </LoadingButton>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </form>
      </Form>
    </div>
  )
}
