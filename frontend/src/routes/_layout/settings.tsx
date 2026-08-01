import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { z } from "zod"

import ChangePassword from "@/components/UserSettings/ChangePassword"
import DeleteAccount from "@/components/UserSettings/DeleteAccount"
import { ProviderSettings } from "@/components/UserSettings/ProviderSettings"
import { UsageSettings } from "@/components/UserSettings/UsageSettings"
import UserInformation from "@/components/UserSettings/UserInformation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import useAuth from "@/hooks/useAuth"

const tabSchema = z.enum([
  "my-profile",
  "password",
  "usage",
  "model",
  "danger-zone",
])
const searchSchema = z.object({
  tab: tabSchema.optional().catch(undefined),
})
type TabValue = z.infer<typeof tabSchema>

export const Route = createFileRoute("/_layout/settings")({
  component: UserSettings,
  validateSearch: searchSchema,
  head: () => ({
    meta: [
      {
        title: "设置 - NoteLLM",
      },
    ],
  }),
})

const tabsConfig = [
  { value: "my-profile", title: "个人资料", component: UserInformation },
  { value: "password", title: "密码", component: ChangePassword },
  { value: "usage", title: "用量", component: UsageSettings },
  { value: "model", title: "模型配置", component: ProviderSettings },
  { value: "danger-zone", title: "危险操作", component: DeleteAccount },
]

function UserSettings() {
  const { user: currentUser } = useAuth()
  const { tab } = Route.useSearch()
  const navigate = useNavigate()

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

      <Tabs
        value={tab ?? "my-profile"}
        onValueChange={(value) =>
          navigate({
            to: "/settings",
            search: {
              tab: value === "my-profile" ? undefined : (value as TabValue),
            },
            replace: true,
          })
        }
      >
        <TabsList>
          {tabsConfig.map((item) => (
            <TabsTrigger key={item.value} value={item.value}>
              {item.title}
            </TabsTrigger>
          ))}
        </TabsList>
        {tabsConfig.map((item) => (
          <TabsContent key={item.value} value={item.value}>
            <item.component />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
