import { createFileRoute } from "@tanstack/react-router"

import ChangePassword from "@/components/UserSettings/ChangePassword"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import { ProviderSettings } from "@/components/UserSettings/ProviderSettings"
import { UsageSettings } from "@/components/UserSettings/UsageSettings"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"

const tabsConfig = [
  { value: "my-profile", title: "个人资料", component: UserInformation },
  { value: "password", title: "密码", component: ChangePassword },
  { value: "usage", title: "用量", component: UsageSettings },
  { value: "model", title: "模型配置", component: ProviderSettings },
  { value: "danger-zone", title: "危险操作", component: DeleteAccount },
]

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  head: () => ({
    meta: [
      {
        title: "设置 - NoteLLM",
      },
    ],
  }),
})

function UserSettings() {
  const { user: currentUser } = useAuth()

  if (!currentUser) {
    return null
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl font-bold tracking-tight">
          用户设置
        </h1>
        <p className="text-muted-foreground">管理你的账户设置与偏好</p>
      </div>

      <Tabs defaultValue="my-profile">
        <TabsList>
          {tabsConfig.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value}>
              {tab.title}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabsConfig.map((tab) => (
          <TabsContent key={tab.value} value={tab.value}>
            <tab.component />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
