import { UsersService } from "@/client"

export const usageApi = {
  get: () => UsersService.readUserUsage(),
}
