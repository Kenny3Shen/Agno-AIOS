import { expect, test } from '@playwright/test'
import { chatOnlyUser, loginAs, mockApis, openAuthed } from './fixtures'

test.describe('shell critical path', () => {
  test('login lands on dashboard; logo is overview entry; sider has no overview item', async ({ page }) => {
    await mockApis(page)
    await loginAs(page)

    await expect(page).toHaveURL(/#\/dashboard/)
    await expect(page.getByRole('heading', { name: '运行概览' })).toBeVisible()

    // Brand is the only explicit overview entry (aria-label), not a sider menu row.
    await expect(page.getByRole('button', { name: '返回运行概览' })).toBeVisible()
    const sider = page.locator('.shell-sider')
    await expect(sider.getByRole('menuitem', { name: '运行概览' })).toHaveCount(0)
    await expect(sider.getByText('智能体', { exact: true })).toBeVisible()
    await expect(sider.getByText('工作台', { exact: true })).toBeVisible()
    await expect(sider.getByText('能力与数据', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: '返回运行概览' }).click()
    await expect(page).toHaveURL(/#\/dashboard/)
  })

  test('agent nav clears session query; deep link opens governance group item', async ({ page }) => {
    await openAuthed(page, '/dashboard')

    await page.goto('/#/chat?session=sess-keep', { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/session=sess-keep/)

    // Menu item for 智能体 always navigates to clean /chat.
    await page.locator('.shell-sider').getByRole('menuitem', { name: /智能体/ }).click()
    await expect(page).toHaveURL(/#\/chat/)
    expect(page.url()).not.toContain('session=')

    // Deep link into a default-collapsed group (governance is 3rd; not in default open pair).
    await page.goto('/#/trace', { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/#\/trace/)
    const sider = page.locator('.shell-sider')
    if (await sider.evaluate((element) => element.classList.contains('ant-layout-sider-collapsed'))) {
      await page.getByRole('button', { name: '折叠或展开导航' }).click()
    }
    await expect(sider.getByText('观测', { exact: true })).toBeVisible()
    await expect(sider.getByText('运行治理', { exact: true })).toBeVisible()
  })

  test('limited scopes drop empty navigation groups', async ({ page }) => {
    await openAuthed(page, '/dashboard', { user: chatOnlyUser })

    const sider = page.locator('.shell-sider')
    await expect(sider.getByText('智能体', { exact: true })).toBeVisible()
    await expect(sider.getByText('工作台', { exact: true })).toBeVisible()
    // No skills/knowledge/etc. scopes → capabilities / governance / intelligence gone.
    await expect(sider.getByText('能力与数据', { exact: true })).toHaveCount(0)
    await expect(sider.getByText('运行治理', { exact: true })).toHaveCount(0)
    await expect(sider.getByText('安全情报', { exact: true })).toHaveCount(0)
    await expect(sider.getByText('知识库', { exact: true })).toHaveCount(0)
    await expect(sider.getByText('观测', { exact: true })).toHaveCount(0)
  })

  test('desktop sider shows account above settings; chat keeps nav expanded', async ({ page }) => {
    await openAuthed(page, '/dashboard')

    await expect(page.locator('.shell-sider')).toBeVisible()
    // Conversations live on the agent page, not the global sider.
    await expect(page.locator('.shell-sider').getByText('对话', { exact: true })).toHaveCount(0)
    await expect(page.locator('.shell-footer .shell-identity')).toBeVisible()
    await expect(page.locator('.shell-footer').getByText('设置', { exact: true })).toBeVisible()

    await page.locator('.shell-sider').getByRole('menuitem', { name: /智能体/ }).click()
    await expect(page).toHaveURL(/#\/chat/)
    // Collapse is user-controlled; entering Chat must not force-collapse the sider.
    await expect(page.locator('.shell-sider.ant-layout-sider-collapsed')).toHaveCount(0)
    await expect(page.locator('.chat-conversations-rail').getByText('对话', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '返回运行概览' })).toBeVisible()
  })
})
