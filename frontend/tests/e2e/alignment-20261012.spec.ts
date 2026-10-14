import { test, expect, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { prepareTask } from './onboarding'
import { captureEvents } from './evidence'

async function enter(page: Page) {
  captureEvents(page)
  const { tokens } = JSON.parse(fs.readFileSync(path.resolve('../artifacts/e2e-current.json'), 'utf8'))
  await page.goto('/enter?seat=03&token=' + tokens['03'])
}
async function state(page: Page) {
  return page.evaluate(async () => (await fetch('/api/v1/workbench/state', { headers: { Authorization: 'Bearer ' + localStorage.getItem('session-token') } })).json())
}
async function end(page: Page) {
  await page.getByRole('button', { name: '结束', exact: true }).click()
  await page.getByRole('button', { name: '确认结束', exact: true }).click()
  await expect(page.getByText('会话已结束，最后保存的草稿已归档。')).toBeVisible()
}

test('全部拒答可继续，四维标准可返回查阅，PDF恢复且多页输入不发送全文', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await enter(page)
  await page.getByRole('button', { name: /^(进入任务|继续任务)$/ }).click()
  await expect(page.getByRole('heading', { name: '开始前的背景信息' })).toBeVisible()
  for (const field of await page.locator('fieldset').all()) await field.getByLabel('不愿回答', { exact: true }).check()
  await page.getByRole('button', { name: '提交并查看任务' }).click()
  await expect(page.locator('.task-tabs button')).toHaveCount(4)
  await expect(page.locator('.task-standards tbody tr')).toHaveCount(4)
  await page.getByRole('button', { name: '教材', exact: true }).click()
  await expect(page.locator('.pdf-page .textLayer span').first()).toContainText('Synthetic')
  await page.getByRole('button', { name: '引用当前页', exact: true }).click()
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(page.getByLabel('教材页序')).toHaveValue('3')
  await page.getByRole('button', { name: '引用当前页', exact: true }).click()
  await page.getByRole('button', { name: '放大教材' }).click()
  await page.getByRole('button', { name: '收起缩略图' }).click()
  await page.screenshot({ path: '../artifacts/implementation-2026-10-12/pdf-reader.png' })
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  await expect(page.locator('.composer')).toContainText('文件第 1 页')
  await expect(page.locator('.composer')).toContainText('文件第 3 页')
  await page.getByRole('button', { name: '教材', exact: true }).click()
  await expect(page.getByLabel('教材页序')).toHaveValue('3')
  await expect(page.getByRole('button', { name: '显示缩略图' })).toBeVisible()
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  await page.getByLabel('给 AI 的消息').fill('Compare selected pages')
  await page.getByRole('button', { name: '发送 ↑', exact: true }).click()
  await expect.poll(async () => (await state(page)).ai_requests[0]?.model_user_text).toContain('Feedback:')
  const request = (await state(page)).ai_requests[0]
  expect(request.input_sources.map((r: { page: number }) => r.page)).toEqual([1, 3])
  expect(request.model_user_text).not.toContain('Interaction: classify')
  await page.getByRole('button', { name: '提交作品', exact: true }).click()
  await page.getByLabel('简要设计说明').fill('Practice animal vocabulary with explanations.')
  await page.getByRole('button', { name: '确认提交', exact: true }).click()
  await expect.poll(async () => (await state(page)).submissions[0]?.status).toBe('SUCCEEDED')
  expect((await state(page)).submissions[0].command.design_rationale).toBe('Practice animal vocabulary with explanations.')
  await end(page)
  expect(errors).toEqual([])
})

test('保存后等待真实加载，编辑与预览双版本、失败与刷新加载分别记录', async ({ page }) => {
  await enter(page)
  await prepareTask(page)
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  const editor = page.getByTestId('code-input')
  await editor.click()
  await page.keyboard.insertText('<button id="quiz">Answer</button>')
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.getByTestId('preview-version')).toContainText('预览版本 v1')
  await editor.click(); await page.keyboard.press('Control+End'); await page.keyboard.insertText('<!-- change -->')
  await expect(page.locator('.editor-panel .panel-heading')).toContainText('编辑版本 v2')
  await expect(page.getByTestId('preview-version')).toContainText('预览版本 v1')
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/preview-content/**', async route => { await gate; await route.continue() })
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.getByTestId('preview-version')).toContainText('预览加载中')
  await expect.poll(async () => (await state(page)).preview_runs.at(-1)?.load_attempts?.at(-1)?.state).toBe('loading')
  release()
  await expect(page.getByTestId('preview-version')).toContainText('预览版本 v2')
  await page.unroute('**/api/v1/preview-content/**')
  await page.route('**/api/v1/preview-content/**', route => route.abort())
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.getByTestId('preview-version')).toContainText('预览不可用', { timeout: 20000 })
  await page.unroute('**/api/v1/preview-content/**')
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.getByTestId('preview-version')).toContainText('预览版本 v2')
  await page.reload()
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  await expect(page.getByTestId('preview-version')).toContainText('预览版本 v2')
  await expect.poll(async () => (await state(page)).preview_runs.at(-1)?.load_attempts?.length).toBe(2)
  await end(page)
})
