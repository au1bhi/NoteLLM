import { isAxiosError } from "axios"

import {
  type Body_login_login_access_token as AccessToken,
  ApiError,
  LoginService,
  MetaService,
  type SignupResult,
  type Token,
  type TurnstilePublic,
  type UserRegister,
  UsersService,
} from "@/client"

async function withChineseNetworkError<T>(
  request: () => Promise<T>,
): Promise<T> {
  try {
    return await request()
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (
      isAxiosError(error) &&
      (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT")
    ) {
      throw new Error("请求超时，请检查网络后重试")
    }
    throw new Error("网络连接失败，请检查网络后重试")
  }
}

export const authApi = {
  getTurnstileConfig: () =>
    withChineseNetworkError<TurnstilePublic>(() => MetaService.getTurnstile()),

  login: (data: AccessToken, turnstileToken?: string) =>
    withChineseNetworkError<Token>(() =>
      LoginService.loginAccessToken({
        formData: data,
        xTurnstileToken: turnstileToken,
      }),
    ),

  signUp: (data: UserRegister, turnstileToken?: string) =>
    withChineseNetworkError<SignupResult>(() =>
      UsersService.registerUser({
        requestBody: data,
        xTurnstileToken: turnstileToken,
      }),
    ),

  recoverPassword: (email: string, turnstileToken?: string) =>
    withChineseNetworkError(() =>
      LoginService.recoverPassword({
        email,
        xTurnstileToken: turnstileToken,
      }),
    ),
}
