import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  createFileRoute,
  Outlet,
  redirect,
  useNavigate,
} from "@tanstack/react-router"
import { LogOut, MailWarning } from "lucide-react"

import { UsersService } from "@/client"
import { Footer } from "@/components/Common/Footer"
import AppSidebar from "@/components/Sidebar/AppSidebar"
import { Button } from "@/components/ui/button"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import useAuth, { isLoggedIn } from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

export const Route = createFileRoute("/_layout")({
  component: Layout,
  beforeLoad: async () => {
    if (!isLoggedIn()) {
      throw redirect({
        to: "/login",
      })
    }
  },
})

function Layout() {
  const { logout, user } = useAuth()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const resendMutation = useMutation({
    mutationFn: () => UsersService.resendVerificationMe(),
    onSuccess: () => {
      showSuccessToast("验证邮件已发送，请查收")
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
    },
  })

  const needsVerification = Boolean(user && !user.is_email_verified)

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="relative">
        <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-2 border-b bg-background/95 px-4 backdrop-blur-xl">
          <SidebarTrigger className="-ml-1 text-muted-foreground" />
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto gap-2 text-muted-foreground hover:text-foreground"
            onClick={logout}
          >
            <LogOut className="size-4" />
            退出登录
          </Button>
        </header>
        {needsVerification && (
          <div className="border-b bg-amber-50 dark:bg-amber-950/40">
            <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-2.5 text-sm md:px-8">
              <MailWarning className="size-4 shrink-0 text-amber-700 dark:text-amber-400" />
              <p className="flex-1 text-amber-900 dark:text-amber-100">
                邮箱尚未验证，部分功能可能受限。
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => resendMutation.mutate()}
                disabled={resendMutation.isPending}
                className="border-amber-300 bg-transparent text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-100 dark:hover:bg-amber-900/40"
              >
                {resendMutation.isPending ? "发送中…" : "重新发送验证邮件"}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate({ to: "/settings" })}
                className="text-amber-900 hover:bg-amber-100 dark:text-amber-100 dark:hover:bg-amber-900/40"
              >
                去设置
              </Button>
            </div>
          </div>
        )}
        <main className="flex-1 p-6 md:p-8">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
        <Footer />
      </SidebarInset>
    </SidebarProvider>
  )
}
