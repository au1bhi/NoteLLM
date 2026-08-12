import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import { useState } from "react"

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
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"
import { type Notebook, notebooksApi } from "@/services/notebooks"
import { extractErrorMessage } from "@/utils"

interface DeleteNotebookProps {
  notebook: Notebook
  triggerClassName?: string
  onDeleted?: () => void
}

export function DeleteNotebook({
  notebook,
  triggerClassName,
  onDeleted,
}: DeleteNotebookProps) {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const mutation = useMutation({
    mutationFn: () => notebooksApi.delete(notebook.id),
    onError: (error: Error) => showErrorToast(extractErrorMessage(error)),
    onSuccess: () => {
      setIsOpen(false)
      showSuccessToast("笔记本已删除")
      onDeleted?.()
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["notebooks"] })
      queryClient.invalidateQueries({ queryKey: ["study-plans"] })
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
          aria-label={`删除 ${notebook.title}`}
          onClick={(event) => event.stopPropagation()}
        >
          <Trash2 className="size-4" />
          <span className="sr-only">删除笔记本</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>删除笔记本</DialogTitle>
          <DialogDescription>
            将永久删除「{notebook.title}」及其全部资料与会话，此操作无法撤销。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={mutation.isPending}>
              取消
            </Button>
          </DialogClose>
          <LoadingButton
            variant="destructive"
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            删除
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
