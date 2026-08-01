import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useEffect, useState } from "react"
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
import { type Notebook, notebooksApi } from "@/services/notebooks"

const formSchema = z.object({
  description: z.string().max(1000).optional(),
  title: z.string().min(1, "标题不能为空").max(255),
})

type FormData = z.infer<typeof formSchema>

interface EditNotebookProps {
  notebook: Notebook
  triggerClassName?: string
}

export function EditNotebook({
  notebook,
  triggerClassName,
}: EditNotebookProps) {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const form = useForm<FormData>({
    defaultValues: {
      description: notebook.description ?? "",
      title: notebook.title,
    },
    resolver: zodResolver(formSchema),
  })

  useEffect(() => {
    if (isOpen) {
      form.reset({
        description: notebook.description ?? "",
        title: notebook.title,
      })
    }
  }, [isOpen, notebook, form])

  const mutation = useMutation({
    mutationFn: (data: FormData) => notebooksApi.update(notebook.id, data),
    onError: (error: Error) => showErrorToast(error.message),
    onSuccess: () => {
      form.reset()
      setIsOpen(false)
      showSuccessToast("笔记本已更新")
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["notebooks"] })
      queryClient.invalidateQueries({ queryKey: ["notebooks", notebook.id] })
    },
  })

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={triggerClassName}
          aria-label={`编辑 ${notebook.title}`}
          onClick={(event) => event.stopPropagation()}
        >
          <Pencil className="size-4" />
          <span className="sr-only">编辑笔记本</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>编辑笔记本</DialogTitle>
          <DialogDescription>修改标题与描述。</DialogDescription>
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
                    <Input autoFocus {...field} />
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
                    <Input placeholder="可选" {...field} />
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
                保存
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
