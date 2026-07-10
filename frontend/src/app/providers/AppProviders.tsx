import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { XProvider } from '@ant-design/x'
import antdEn from 'antd/locale/en_US'
import antdZh from 'antd/locale/zh_CN'
import xEn from '@ant-design/x/locale/en_US'
import xZh from '@ant-design/x/locale/zh_CN'
import { App as AntApp, theme } from 'antd'
import i18n from '@/shared/i18n'

type LocaleCode = 'zh-CN' | 'en-US'
interface Preferences { dark: boolean; locale: LocaleCode; toggleTheme: () => void; toggleLocale: () => void }
const PreferencesContext = createContext<Preferences | null>(null)

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false }, mutations: { retry: false } } })

export const usePreferences = () => {
  const value = useContext(PreferencesContext)
  if (!value) throw new Error('Preferences provider is missing')
  return value
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState(() => localStorage.getItem('theme') !== 'light')
  const [locale, setLocale] = useState<LocaleCode>(() => localStorage.getItem('locale') === 'en-US' ? 'en-US' : 'zh-CN')
  const preferences = useMemo<Preferences>(() => ({
    dark,
    locale,
    toggleTheme: () => setDark((value) => { const next = !value; localStorage.setItem('theme', next ? 'dark' : 'light'); return next }),
    toggleLocale: () => setLocale((value) => { const next = value === 'zh-CN' ? 'en-US' : 'zh-CN'; localStorage.setItem('locale', next); void i18n.changeLanguage(next); document.documentElement.lang = next; return next }),
  }), [dark, locale])

  document.documentElement.classList.toggle('dark', dark)
  return (
    <QueryClientProvider client={queryClient}>
      <PreferencesContext.Provider value={preferences}>
        <XProvider
          locale={{ ...(locale === 'zh-CN' ? antdZh : antdEn), ...(locale === 'zh-CN' ? xZh : xEn) }}
          theme={{
            algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
            token: { colorPrimary: '#2f77d4', colorInfo: '#2f77d4', colorSuccess: '#2da76c', colorWarning: '#c88a22', colorError: '#df3f36', borderRadius: 6, fontFamily: 'Inter, Fira Sans, Microsoft YaHei, system-ui, sans-serif' },
          }}
        >
          <AntApp>{children}</AntApp>
        </XProvider>
      </PreferencesContext.Provider>
    </QueryClientProvider>
  )
}
