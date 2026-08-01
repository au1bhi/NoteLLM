import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
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
import useCustomToast from "@/hooks/useCustomToast"
import { cn } from "@/lib/utils"
import { notebooksApi } from "@/services/notebooks"
import { extractErrorMessage } from "@/utils"

const formSchema = z.object({
  description: z.string().max(1000).optional(),
  title: z.string().min(1, "请输入笔记本标题").max(255),
})

type FormData = z.infer<typeof formSchema>

interface AddNotebookProps {
  compact?: boolean
  triggerClassName?: string
}

export function AddNotebook({
  compact = false,
  triggerClassName,
}: AddNotebookProps) {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const form = useForm<FormData>({
    defaultValues: { description: "", title: "" },
    resolver: zodResolver(formSchema),
  })
  const mutation = useMutation({
    mutationFn: notebooksApi.create,
    onError: (error: Error) => showErrorToast(extractErrorMessage(error)),
    onSuccess: () => {
      form.reset()
      setIsOpen(false)
      showSuccessToast("笔记本已创建")
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["notebooks"] }),
  })

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button
          className={cn(
            compact &&
              "h-8 w-full justify-start gap-2 rounded-lg bg-brand-gradient text-white shadow-soft transition-all hover:opacity-95 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-2",
            triggerClassName,
          )}
        >
          <Plus className="size-4 shrink-0" />
          <span
            className={cn(compact && "group-data-[collapsible=icon]:hidden")}
          >
            新建笔记本
          </span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>创建笔记本</DialogTitle>
          <DialogDescription>
            把相关的学习资料与会话整理在一起。
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((data) => mutation.mutate(data))}
            className="grid gap-4"
          >
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>标题</FormLabel>
                  <FormControl>
                    <Input autoFocus placeholder="例如：机器学习" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>描述</FormLabel>
                  <FormControl>
                    <Input placeholder="可选说明" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  取消
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                创建
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
