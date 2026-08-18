import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"

import { UsersService } from "@/client"
import { handleError } from "@/utils"
import useCustomToast from "./useCustomToast"

// Server-side resend is rate limited (3 per 5 minutes); reflect that in the UI
// so a user mashing the button gets a countdown instead of a 429 toast.
const RESEND_COOLDOWN_SECONDS = 60

/**
 * Resend the email-verification message with a short UI cooldown.
 *
 * Pass `email` when the user is not authenticated (post-signup screen);
 * otherwise the signed-in user's address is used (banner / settings).
 */
export function useResendEmail(email?: string) {
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()
  const [cooldown, setCooldown] = useState(0)
  const submitLock = useRef(false)

  const mutation = useMutation({
    mutationFn: () =>
      email
        ? UsersService.resendVerification({ requestBody: { email } })
        : UsersService.resendVerificationMe(),
    onSuccess: () => {
      showSuccessToast(
        "验证邮件已提交发送，若几分钟内未收到，请检查垃圾箱或稍后重试",
      )
      setCooldown(RESEND_COOLDOWN_SECONDS)
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
    },
    onError: handleError.bind(showErrorToast),
    onSettled: () => {
      submitLock.current = false
    },
  })

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setInterval(() => setCooldown((c) => c - 1), 1000)
    return () => clearInterval(timer)
  }, [cooldown])

  return {
    resend: () => {
      if (submitLock.current || mutation.isPending || cooldown > 0) return
      submitLock.current = true
      mutation.mutate()
    },
    isPending: mutation.isPending,
    cooldown,
    disabled: mutation.isPending || cooldown > 0,
  }
}
