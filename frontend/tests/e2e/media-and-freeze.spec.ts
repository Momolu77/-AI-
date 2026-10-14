import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { prepareTask } from './onboarding'
import { captureEvents } from './evidence'

test.beforeEach(({ page }) => {
  captureEvents(page)
})

function entry(seat: string) {
  const { tokens } = JSON.parse(
    fs.readFileSync(path.resolve('../artifacts/e2e-current.json'), 'utf8'),
  )
  return `/enter?seat=${seat}&token=${tokens[seat]}`
}
test('视频不自动播放、暂停后重开保留位置、404 不阻止进入', async ({ page }) => {
  await page.goto(entry('03'))
  await prepareTask(page)
  await page.getByRole('button', { name: '示例', exact: true }).click()
  await page.getByRole('button', { name: /本地交互示意/ }).click()
  const video = page.locator('video')
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThan(0)
  expect(await video.evaluate((v: HTMLVideoElement) => v.paused)).toBe(true)
  await video.evaluate((v: HTMLVideoElement) => v.play())
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime))
    .toBeGreaterThan(1.2)
  await video.evaluate((v: HTMLVideoElement) => v.pause())
  const position = await video.evaluate((v: HTMLVideoElement) => v.currentTime)
  await page.getByRole('button', { name: '关闭示例' }).click()
  await page.getByRole('button', { name: /本地交互示意/ }).click()
  await expect
    .poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime))
    .toBeCloseTo(position, 0)
  expect(await video.evaluate((v: HTMLVideoElement) => v.paused)).toBe(true)
  await page.getByRole('button', { name: '关闭示例' }).click()
  await page.route('**/media/examples/**', (route) =>
    route.fulfill({ status: 404, body: 'missing' }),
  )
  await page.getByRole('button', { name: /本地交互示意/ }).click()
  await expect(page.getByText('视频暂时无法加载。')).toBeVisible()
  await page.getByRole('button', { name: '关闭示例' }).click()
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  await expect(page.getByTestId('code-input')).toBeVisible()
  await page.getByRole('button', { name: '结束', exact: true }).click()
  await page.getByRole('button', { name: '确认结束', exact: true }).click()
  await expect(page.getByText('会话已结束，最后保存的草稿已归档。')).toBeVisible()
})

test('提交期间继续编辑，快照固定为确认时文本，下一次提交保存新版本', async ({ page }) => {
  await page.goto(entry('03'))
  await prepareTask(page)
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  const editor = page.getByTestId('code-input')
  await editor.click()
  await page.keyboard.insertText('<h1>版本 A</h1>')
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let captured = ''
  await page.route('**/api/v1/submissions', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue()
      return
    }
    captured = route.request().postDataJSON().code
    await gate
    await route.continue()
  })
  await page.getByRole('button', { name: '提交作品', exact: true }).click()
  await page.getByRole('button', { name: '确认提交', exact: true }).click()
  await expect.poll(() => captured).toBe('<h1>版本 A</h1>')
  await editor.click()
  await page.keyboard.press('Control+a')
  await page.keyboard.insertText('<h1>版本 B</h1>')
  // Allow the real checkpoint to overtake the delayed submission, exercising historical revision insert.
  await page.locator('.editor-status button').click()
  await expect(page.locator('.editor-status button')).toHaveText('已保存')
  release()
  await expect(page.getByText('作品提交成功。你可以继续修改并再次提交。')).toBeVisible()
  const submissions = await page.evaluate(async () =>
    (
      await fetch('/api/v1/submissions', {
        headers: { Authorization: 'Bearer ' + localStorage.getItem('session-token') },
      })
    ).json(),
  )
  expect(submissions.submissions[0].command.code).toBe('<h1>版本 A</h1>')
  expect(submissions.submissions[0].status).toBe('SUCCEEDED')
  await expect(editor).toContainText('版本 B')
  await page.unroute('**/api/v1/submissions')
  await page.getByRole('button', { name: '提交作品', exact: true }).click()
  await page.getByRole('button', { name: '确认提交', exact: true }).click()
  await expect(page.getByText('已成功提交 2 次')).toBeVisible()
  await page.getByRole('button', { name: '结束', exact: true }).click()
  await page.getByRole('button', { name: '确认结束', exact: true }).click()
  await expect(page.getByText('会话已结束，最后保存的草稿已归档。')).toBeVisible()
})
