import { useQuery } from "@tanstack/react-query"
import { Link, useRouterState } from "@tanstack/react-router"
import { ArrowRight, BookOpen } from "lucide-react"

import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { notebooksApi } from "@/services/notebooks"

export function RecentNotebooks() {
  const { isMobile, setOpenMobile } = useSidebar()
  const router = useRouterState()
  const { data } = useQuery({
    queryKey: ["notebooks"],
    queryFn: notebooksApi.list,
  })

  const notebooks = data?.data ?? []
  const recent = [...notebooks]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 5)

  if (recent.length === 0) return null

  const handleClick = () => {
    if (isMobile) setOpenMobile(false)
  }

  return (
    <SidebarGroup>
      <SidebarGroupLabel>最近笔记本</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {recent.map((notebook) => {
            const isActive =
              router.location.pathname === `/notebooks/${notebook.id}`
            return (
              <SidebarMenuItem key={notebook.id}>
                <SidebarMenuButton
                  isActive={isActive}
                  tooltip={notebook.title}
                  asChild
                >
                  <Link
                    to="/notebooks/$notebookId"
                    params={{ notebookId: notebook.id }}
                    onClick={handleClick}
                  >
                    <BookOpen />
                    <span>{notebook.title}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            )
          })}
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="查看全部笔记本"
              asChild
              className="text-muted-foreground"
            >
              <Link to="/notebooks" onClick={handleClick}>
                <ArrowRight />
                <span>查看全部笔记本</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}
