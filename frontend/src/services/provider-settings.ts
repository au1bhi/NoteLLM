import {
  type UserProviderSettingsCreate,
  type UserProviderSettingsPublic,
  UsersService,
} from "@/client"

export const providerSettingsApi = {
  get: () => UsersService.readUserProviderSettings(),
  update: (input: UserProviderSettingsCreate) =>
    UsersService.upsertUserProviderSettings({ requestBody: input }),
  clear: () => UsersService.deleteUserProviderSettings(),
  fetchModels: (base_url: string, api_key: string) =>
    UsersService.fetchAvailableModels({ requestBody: { base_url, api_key } }),
}

export type ProviderSettings = UserProviderSettingsPublic
