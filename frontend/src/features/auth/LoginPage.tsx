import { useQueryClient } from '@tanstack/react-query'
import { useRouter, useRouterState } from '@tanstack/react-router'
import { AuthPage } from './AuthPage'
import { authKeys } from './queries'
import { DEFAULT_AUTHENTICATED_PATH, sanitizeNextPath } from './routing'

export function LoginPage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const searchStr = useRouterState({ select: (state) => state.location.searchStr })
  const next = sanitizeNextPath(new URLSearchParams(searchStr).get('next'))

  const onAuthenticated = async () => {
    await queryClient.invalidateQueries({ queryKey: authKeys.current })
    router.history.replace(next ?? DEFAULT_AUTHENTICATED_PATH)
  }

  return <AuthPage onAuthenticated={onAuthenticated} />
}
