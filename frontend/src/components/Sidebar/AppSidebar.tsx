import { BookOpen, Home, Users } from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import { AddNotebook } from "@/components/Notebooks/AddNotebook"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarSeparator,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { RecentNotebooks } from "./RecentNotebooks"
import { User } from "./User"

const baseItems: Item[] = [
  { icon: Home, title: "首页", path: "/" },
  { icon: BookOpen, title: "笔记本", path: "/notebooks" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const items = currentUser?.is_superuser
    ? [...baseItems, { icon: Users, title: "管理", path: "/admin" }]
    : baseItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 pb-3 pt-5 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:pb-4 group-data-[collapsible=icon]:pt-2">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <div className="px-3 pb-1 pt-1 group-data-[collapsible=icon]:px-2">
          <AddNotebook compact />
        </div>
        <SidebarSeparator className="mx-3" />
        <SidebarGroup>
          <SidebarGroupLabel>菜单</SidebarGroupLabel>
          <SidebarGroupContent>
            <Main items={items} />
          </SidebarGroupContent>
        </SidebarGroup>
        <RecentNotebooks />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
