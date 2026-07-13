import { useState } from 'react'
import { App, Button, Card, Form, Input, Space, Typography } from 'antd'
import { GithubOutlined, LockOutlined, MailOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { getOAuthAuthorization, getOAuthProviders, login } from './api'
import { setToken } from '@/shared/auth/storage'

export function AuthPage({ onAuthenticated }: { onAuthenticated: () => Promise<void> }) {
  const { message } = App.useApp()
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [providers, setProviders] = useState<string[]>([])

  const submit = async ({ email, password }: { email: string; password: string }) => {
    setLoading(true)
    try {
      const token = await login(email, password)
      setToken(token.access_token)
      await onAuthenticated()
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('auth:failed'))
    } finally {
      setLoading(false)
    }
  }

  const loadProviders = async () => {
    try {
      setProviders(await getOAuthProviders())
    } catch {
      setProviders([])
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-signal auth-enter auth-enter-signal" aria-hidden="true">
        <span>CONTROL PLANE</span>
        <i />
        <span>IDENTITY GATE</span>
        <i />
        <span>TAIS/01</span>
      </section>
      <Card className="auth-card auth-enter auth-enter-card" variant="outlined">
        <div className="brand-lockup auth-enter auth-enter-brand">
          <span className="brand-mark">T</span>
          <div>
            <strong>T.A.I.S</strong>
            <small>Trinity AI Security</small>
          </div>
        </div>
        <div className="auth-enter auth-enter-copy">
          <Typography.Title level={2}>{t('auth:title')}</Typography.Title>
          <Typography.Paragraph type="secondary">{t('auth:subtitle')}</Typography.Paragraph>
        </div>
        <Form
          className="auth-enter auth-enter-form"
          layout="vertical"
          onFinish={submit}
          requiredMark={false}
          initialValues={{ email: 'admin@example.com' }}
        >
          <Form.Item name="email" label={t('auth:email')} rules={[{ required: true }, { type: 'email' }]}>
            <Input prefix={<MailOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label={t('auth:password')} rules={[{ required: true }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} block>
            {t('auth:signIn')}
          </Button>
        </Form>
        <Space orientation="vertical" className="oauth-list">
          {!providers.length && (
            <Button type="text" onClick={() => void loadProviders()}>
              SSO providers
            </Button>
          )}
          {providers.map((provider) => (
            <Button
              key={provider}
              icon={<GithubOutlined />}
              onClick={async () => {
                window.location.assign(await getOAuthAuthorization(provider))
              }}
            >
              {provider}
            </Button>
          ))}
        </Space>
      </Card>
    </main>
  )
}
