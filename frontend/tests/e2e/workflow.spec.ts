import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { captureEvents } from './evidence'
const state = () =>
  JSON.parse(fs.readFileSync(path.resolve('../artifacts/e2e-current.json'), 'utf8')) as {
    tokens: Record<string, string>
    data_dir: string
  }
async function enter(page: Page, seat: string) {
  captureEvents(page)
  await page.goto(`/enter?seat=${seat}&token=${state().tokens[seat]}`)
  await expect(page.getByRole('button', { name: '去工作区', exact: true })).toBeVisible()
}
async function work(page: Page) {
  await page.getByRole('button', { name: '去工作区', exact: true }).click()
}
async function stateAPI(page: Page) {
  return page.evaluate(async () =>
    (
      await fetch('/api/v1/workbench/state', {
        headers: { Authorization: 'Bearer ' + localStorage.getItem('session-token') },
      })
    ).json(),
  )
}
async function setCode(page: Page, code: string) {
  const editor = page.getByTestId('code-input')
  await editor.click()
  await page.keyboard.press('Control+a')
  await page.keyboard.insertText(code)
}
const game =
  '<!DOCTYPE html><meta charset="utf-8"><button id="counter" onclick="this.textContent=Number(this.textContent)+1">0</button><script>console.log("ready");</script>'

test('完整制作：AI、附件、复制、手动运行、计划保活、错误、提交和恢复', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  await enter(page, '01')
  await page.screenshot({ path: '../artifacts/task-page.png', fullPage: true })
  await work(page)
  await page.getByLabel('给 AI 的消息').fill('请帮我制作词汇游戏')
  await page
    .locator('input[type=file]')
    .setInputFiles({
      name: 'unit.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('Unit 1: apple banana orange pear grape peach lemon mango'),
    })
  await expect(page.getByText('可发送', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '发送 ↑' }).click()
  await expect(page.getByRole('button', { name: '复制代码', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '复制代码', exact: true }).click()
  await page.getByTestId('code-input').click()
  await page.keyboard.press('Control+v')
  await expect(page.getByTestId('code-input')).toContainText('词汇翻牌')
  await expect(page.locator('iframe')).toHaveCount(0)
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(
    page.frameLocator('iframe').getByRole('button', { name: 'apple', exact: true }),
  ).toBeVisible()
  await page.frameLocator('iframe').getByRole('button', { name: 'apple', exact: true }).click()
  await expect(page.frameLocator('iframe').locator('#count')).toHaveText('1')
  await setCode(page, game)
  await expect(page.getByText('代码已修改，运行后更新预览')).toBeVisible()
  await expect(page.frameLocator('iframe').locator('#count')).toHaveText('1')
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await page.frameLocator('iframe').locator('#counter').click()
  await expect(page.frameLocator('iframe').locator('#counter')).toHaveText('1')
  await page.getByRole('button', { name: '我的计划', exact: true }).click()
  await page.getByLabel('计划内容').fill('先明确教材单元，再验证点击反馈。')
  await page.getByRole('button', { name: '收起计划' }).click()
  await page.getByRole('button', { name: '← 查看任务' }).click()
  await work(page)
  await expect(page.frameLocator('iframe').locator('#counter')).toHaveText('1')
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.frameLocator('iframe').locator('#counter')).toHaveText('0')
  await setCode(
    page,
    '<button onclick="throw new Error(\'点击异常\')">触发错误</button><script>Promise.reject(new Error("异步异常"))</script>',
  )
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.locator('.console-content')).toContainText('异步异常')
  await page.frameLocator('iframe').getByRole('button', { name: '触发错误' }).click()
  await expect(page.locator('.console-content')).toContainText('点击异常')
  await page.getByRole('button', { name: '复制错误' }).first().click()
  await setCode(page, game)
  await page.getByRole('button', { name: '提交作品', exact: true }).click()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await page.getByRole('button', { name: '提交作品', exact: true }).click()
  await page.getByRole('button', { name: '确认提交', exact: true }).click()
  await expect(page.getByText('作品提交成功。你可以继续修改并再次提交。')).toBeVisible()
  const state1 = await stateAPI(page)
  expect(
    state1.submissions.filter((s: { status: string }) => s.status === 'SUCCEEDED'),
  ).toHaveLength(1)
  expect(state1.submissions[0].command.code).toBe(game)
  await setCode(page, game + '<!-- version B -->')
  await page.getByRole('button', { name: '提交作品', exact: true }).click()
  await page.getByRole('button', { name: '确认提交', exact: true }).click()
  await expect.poll(async () => (await stateAPI(page)).submissions.length).toBe(2)
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.frameLocator('iframe').locator('#counter')).toHaveText('0')
  await page.screenshot({ path: '../artifacts/workbench.png', fullPage: true })
  await page.reload()
  await work(page)
  await expect(page.getByTestId('code-input')).toContainText('version B')
  await expect(page.locator('iframe')).toHaveCount(0)
  await page.getByRole('button', { name: '我的计划', exact: true }).click()
  await expect(page.getByLabel('计划内容')).toHaveValue('先明确教材单元，再验证点击反馈。')
  // Browser reports errors intentionally thrown by sandbox fixtures too.
  expect(errors.filter((e) => !e.includes('异常'))).toEqual([])
  await page.getByRole('button', { name: '结束', exact: true }).click()
  await page.getByRole('button', { name: '确认结束', exact: true }).click()
  await expect(page.getByText('会话已结束，最后保存的草稿已归档。')).toBeVisible()
})

test('断开本地 API：草稿、旧预览和事件保留，恢复后补传', async ({ page }) => {
  await enter(page, '02')
  await work(page)
  await setCode(page, game)
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.frameLocator('iframe').locator('#counter')).toBeVisible()
  await page.route('**/api/v1/**', (route) => route.abort())
  await setCode(page, game + '<!-- offline -->')
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('本地服务')
  await expect(page.frameLocator('iframe').locator('#counter')).toHaveText('0')
  await page.getByRole('button', { name: '我的计划', exact: true }).click()
  await page.getByLabel('计划内容').fill('离线计划')
  await page.getByRole('button', { name: '收起计划' }).click()
  await page.unroute('**/api/v1/**')
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  await page.getByRole('button', { name: '我的计划', exact: true }).click()
  await page.locator('.plan-status').click()
  await expect.poll(async () => (await stateAPI(page)).code.content).toContain('offline')
  await expect(page.getByRole('button', { name: '0 条待同步', exact: true })).toBeVisible({
    timeout: 15000,
  })
  await page.reload()
  await work(page)
  await expect(page.getByTestId('code-input')).toContainText('offline')
  await page.getByRole('button', { name: '结束', exact: true }).click()
  await page.getByRole('button', { name: '确认结束', exact: true }).click()
  await expect(page.getByText('会话已结束，最后保存的草稿已归档。')).toBeVisible()
})

test('三个隔离浏览器上下文不会串会话，同一会话重复标签页禁止编辑', async ({ browser }) => {
  const contexts = await Promise.all([
    browser.newContext(),
    browser.newContext(),
    browser.newContext(),
  ])
  const pages = await Promise.all(contexts.map((c) => c.newPage()))
  for (let i = 0; i < 3; i++) {
    await enter(pages[i]!, String(i + 1).padStart(2, '0'))
    await work(pages[i]!)
    await setCode(pages[i]!, `<p>isolated-seat-${i + 1}</p>`)
    await pages[i]!.getByRole('button', { name: '▶ 运行', exact: true }).click()
  }
  for (let i = 0; i < 3; i++) {
    expect((await stateAPI(pages[i]!)).code.content).toBe(`<p>isolated-seat-${i + 1}</p>`)
  }
  const duplicate = await contexts[0]!.newPage()
  await duplicate.goto('/task')
  await expect(
    duplicate.getByText('此会话已在另一个标签页打开。请关闭重复标签页后重新加载。'),
  ).toBeVisible()
  await duplicate.close()
  for (const page of pages) {
    await page.getByRole('button', { name: '结束', exact: true }).click()
    await page.getByRole('button', { name: '确认结束', exact: true }).click()
    await expect(page.getByText('会话已结束，最后保存的草稿已归档。')).toBeVisible()
  }
  await Promise.all(contexts.map((c) => c.close()))
})
