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
}

export type ProviderSettings = UserProviderSettingsPublic
