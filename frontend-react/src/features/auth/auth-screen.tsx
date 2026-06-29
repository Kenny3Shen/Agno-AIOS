import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  ArrowRight,
  Github,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from 'lucide-react'

import { Button } from '#/components/ui/button.tsx'
import { Input } from '#/components/ui/input.tsx'
import { Label } from '#/components/ui/label.tsx'
import { fetchOAuthProviders, requestOAuthAuthorization } from '#/lib/auth.ts'
import type { OAuthProvider } from '#/lib/auth.ts'
import { cn } from '#/lib/utils.ts'

import { useAuth } from './auth-provider.tsx'

type AuthMode = 'login' | 'register'

const providerLabels: Record<string, string> = {
  github: 'GitHub',
  google: 'Google',
  microsoft: 'Microsoft',
}

function providerLabel(provider: OAuthProvider) {
  return providerLabels[provider] ?? provider
}

export function AuthScreen() {
  const auth = useAuth()
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const [providers, setProviders] = useState<OAuthProvider[]>([])
  const [pendingProvider, setPendingProvider] = useState<string | null>(null)
  const [isSubmitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    void fetchOAuthProviders().then((nextProviders) => {
      if (!cancelled) setProviders(nextProviders)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const isRegister = mode === 'register'

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice(null)
    setSubmitting(true)
    void (async () => {
      try {
        if (isRegister) {
          await auth.register(email, password)
        } else {
          await auth.login(email, password)
        }
      } catch (error) {
        setNotice(error instanceof Error ? error.message : '认证请求失败。')
      } finally {
        setSubmitting(false)
      }
    })()
  }

  async function startOAuth(provider: OAuthProvider) {
    setNotice(null)
    setPendingProvider(provider)
    try {
      const authorizationUrl = await requestOAuthAuthorization(provider)
      window.location.assign(authorizationUrl)
    } catch (error) {
      setNotice(
        error instanceof Error ? error.message : 'OAuth 授权初始化失败。',
      )
      setPendingProvider(null)
    }
  }

  return (
    <main className="min-h-dvh overflow-hidden bg-[#071014] text-white">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_18%,rgba(56,189,248,0.22),transparent_28%),radial-gradient(circle_at_82%_12%,rgba(16,185,129,0.16),transparent_24%),linear-gradient(135deg,#071014_0%,#0d1821_52%,#eef4f8_52%,#f8fafc_100%)]" />
      <div className="relative grid min-h-dvh grid-cols-1 lg:grid-cols-[minmax(0,1fr)_480px]">
        <section className="hidden min-h-0 flex-col justify-between p-10 lg:flex">
          <div className="flex items-center gap-3">
            <div className="grid size-11 place-items-center rounded-xl border border-cyan-200/20 bg-cyan-200/10 text-cyan-100">
              <ShieldCheck className="size-5" />
            </div>
            <div>
              <div className="text-xs font-semibold tracking-[0.28em] text-cyan-100/68 uppercase">
                AGNO AIOS
              </div>
              <div className="text-lg font-black tracking-[-0.03em]">
                AI 信息安全中台
              </div>
            </div>
          </div>

          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200/15 bg-white/[0.04] px-3 py-1 text-xs text-cyan-100/72">
              <KeyRound className="size-3.5" />
              FastAPI Users JWT / OAuth2
            </div>
            <h1 className="mt-8 max-w-4xl text-[clamp(3rem,4.6vw,5.2rem)] leading-[0.98] font-black tracking-[-0.07em]">
              <span className="block">登录后进入</span>
              <span className="block">安全运营工作台</span>
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300/78">
              认证层对齐后端 FastAPI Users，统一承接账号注册、JWT 登录以及
              GitHub / Google / Microsoft OAuth2 登录入口。
            </p>
          </div>

          <div className="grid max-w-3xl grid-cols-3 gap-3">
            {['Agent 对话', 'Trace 观测', 'MCP 工具'].map((item) => (
              <div
                className="rounded-2xl border border-white/10 bg-slate-950/78 p-4 text-white shadow-[0_18px_50px_rgba(0,0,0,0.24)] backdrop-blur"
                key={item}
              >
                <div className="text-sm font-semibold text-white">{item}</div>
                <div className="mt-2 h-1 rounded-full bg-cyan-200/45" />
              </div>
            ))}
          </div>
        </section>

        <section className="flex min-h-dvh items-center justify-center p-4 sm:p-8">
          <div className="w-full max-w-[440px] rounded-[2rem] border border-slate-200 bg-white p-5 text-slate-950 shadow-[0_24px_80px_rgba(15,23,42,0.18)] sm:p-7">
            <div className="lg:hidden">
              <div className="flex items-center gap-3">
                <div className="grid size-10 place-items-center rounded-xl bg-slate-950 text-white">
                  <ShieldCheck className="size-4.5" />
                </div>
                <div>
                  <div className="text-xs font-semibold tracking-[0.22em] text-slate-500 uppercase">
                    AGNO AIOS
                  </div>
                  <div className="font-black">AI 信息安全中台</div>
                </div>
              </div>
            </div>

            <div className="mt-6 flex rounded-xl border border-slate-200 bg-slate-50 p-1 lg:mt-0">
              {(['login', 'register'] as const).map((item) => (
                <button
                  className={cn(
                    'h-10 flex-1 rounded-lg text-sm font-semibold transition-colors',
                    mode === item
                      ? 'bg-slate-950 text-white shadow-sm'
                      : 'text-slate-500 hover:text-slate-950',
                  )}
                  key={item}
                  onClick={() => {
                    setMode(item)
                    setNotice(null)
                  }}
                  type="button"
                >
                  {item === 'login' ? '登录' : '注册'}
                </button>
              ))}
            </div>

            <div className="mt-7">
              <h2 className="text-3xl font-black tracking-[-0.05em]">
                {isRegister ? '创建账号' : '欢迎回来'}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {isRegister
                  ? '密码至少 8 位，注册成功后会自动登录。'
                  : '使用邮箱和密码登录后进入 AI 信息安全中台。'}
              </p>
            </div>

            <form className="mt-6 flex flex-col gap-4" onSubmit={submit}>
              <div className="flex flex-col gap-2">
                <Label htmlFor="auth-email">邮箱</Label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
                  <Input
                    autoComplete="email"
                    className="h-11 pl-9"
                    id="auth-email"
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="secops@example.com"
                    required
                    type="email"
                    value={email}
                  />
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="auth-password">密码</Label>
                <div className="relative">
                  <LockKeyhole className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
                  <Input
                    autoComplete={
                      isRegister ? 'new-password' : 'current-password'
                    }
                    className="h-11 pl-9"
                    id="auth-password"
                    minLength={8}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="至少 8 位"
                    required
                    type="password"
                    value={password}
                  />
                </div>
              </div>

              {notice ? (
                <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                  {notice}
                </div>
              ) : null}

              <Button
                className="h-11 rounded-xl bg-slate-950 text-white hover:bg-slate-800"
                disabled={isSubmitting}
                type="submit"
              >
                {isSubmitting ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <ArrowRight className="size-4" />
                )}
                {isRegister ? '注册并进入' : '登录中台'}
              </Button>
            </form>

            <div className="mt-6 border-t border-slate-200 pt-5">
              <div className="text-center text-xs font-medium text-slate-400">
                OAuth2 登录
              </div>
              <div className="mt-3 grid gap-2">
                {providers.length ? (
                  providers.map((provider) => (
                    <Button
                      className="h-10 rounded-xl"
                      disabled={pendingProvider !== null}
                      key={provider}
                      onClick={() => void startOAuth(provider)}
                      type="button"
                      variant="outline"
                    >
                      <Github className="size-4" />
                      使用 {providerLabel(provider)} 登录
                    </Button>
                  ))
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-center text-xs leading-5 text-slate-500">
                    后端未配置 OAuth Provider 时，仅显示邮箱密码登录。
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  )
}
