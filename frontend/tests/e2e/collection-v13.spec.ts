import { test, expect, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { prepareTask } from './onboarding'
import { captureEvents } from './evidence'
async function state(page: Page) {
  return page.evaluate(async () => {
    const r = await fetch('/api/v1/workbench/state', {
      headers: { Authorization: 'Bearer ' + localStorage.getItem('session-token') },
    })
    return r.json()
  })
}
test('四页、页级引用、逐项提议、过期版本保护及同一预览全屏保活', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  captureEvents(page)
  const { tokens } = JSON.parse(
    fs.readFileSync(path.resolve('../artifacts/e2e-current.json'), 'utf8'),
  )
  await page.goto('/enter?seat=01&token=' + tokens['01'])
  await prepareTask(page)
  await page.getByRole('button', { name: '教材', exact: true }).click()
  await page.getByRole('button', { name: '我的备课记录', exact: true }).click()
  await expect(page.getByLabel('备课记录内容')).toBeVisible()
  await expect(page.getByTestId('code-input')).toBeHidden()
  await page.getByRole('button', { name: '收起备课记录', exact: true }).click()
  await expect(page.locator('.resource-reader canvas')).toHaveCount(3)
  await page.getByRole('button', { name: '引用当前页', exact: true }).click()
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  await expect(page.locator('.composer')).toContainText('资料引用')
  await page.getByLabel('给 AI 的消息').fill('制作课堂互动网站')
  await page.getByRole('button', { name: '发送 ↑', exact: true }).click()
  await page.getByRole('button', { name: '任务', exact: true }).click()
  await expect.poll(async () => (await state(page)).ai_proposals.length).toBe(1)
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  const first = page.locator('.proposal-card').first()
  await first.getByRole('button', { name: '查看改动', exact: true }).click()
  await first.getByRole('button', { name: '接受提议', exact: true }).click()
  expect((await state(page)).code.content).toBe('')
  const editor = page.getByTestId('code-input')
  await editor.click()
  await page.keyboard.insertText('<!-- local edit 😀 -->')
  await first.getByRole('button', { name: '应用到编辑器', exact: true }).click()
  await expect(first).toContainText('代码已变更')
  await expect(editor).toContainText('local edit')
  await page.getByLabel('给 AI 的消息').fill('根据目前代码重新给出完整提议')
  await page.getByRole('button', { name: '发送 ↑', exact: true }).click()
  const second = page.locator('.proposal-card').nth(1)
  await second.getByRole('button', { name: '接受提议', exact: true }).click()
  await second.getByRole('button', { name: '应用到编辑器', exact: true }).click()
  await expect(second).toContainText('已应用')
  await expect(page.locator('iframe')).toHaveCount(0)
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  const button = page
    .frameLocator('iframe[title="网站预览"]')
    .getByRole('button', { name: 'apple', exact: true })
  await button.click()
  await expect(page.frameLocator('iframe[title="网站预览"]').locator('#count')).toHaveText('1')
  const run = (await state(page)).preview_runs[0].id
  const layoutRequest = page.waitForRequest(
    (r) =>
      r.url().endsWith('/events/batch') &&
      r
        .postDataJSON()
        .events.some(
          (e: { event_name: string; payload: { change_reason?: string } }) =>
            e.event_name === 'ui_region_visibility_changed' &&
            e.payload.change_reason === 'planner_open',
        ),
  )
  await page.getByRole('button', { name: '我的备课记录', exact: true }).click()
  const layout = (await layoutRequest)
    .postDataJSON()
    .events.find(
      (e: { event_name: string; payload: { change_reason?: string } }) =>
        e.event_name === 'ui_region_visibility_changed' &&
        e.payload.change_reason === 'planner_open',
    )
  expect(
    layout.payload.regions.find((r: { region_id: string }) => r.region_id === 'preview')
      .occluded_bounds,
  ).toHaveLength(1)
  await page.getByRole('button', { name: '收起备课记录', exact: true }).click()
  await page.getByRole('button', { name: '全屏预览', exact: true }).click()
  await expect(page.getByTestId('code-input')).toBeHidden()
  await expect(page.frameLocator('iframe[title="网站预览"]').locator('#count')).toHaveText('1')
  await page.getByRole('button', { name: '退出全屏', exact: true }).click()
  await page.getByRole('button', { name: '任务列表', exact: true }).click()
  await page.getByRole('button', { name: /^(进入任务|继续任务)$/ }).click()
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  await expect(page.frameLocator('iframe[title="网站预览"]').locator('#count')).toHaveText('1')
  expect((await state(page)).preview_runs.map((r: { id: string }) => r.id)).toEqual([run])
  await page.getByRole('button', { name: '结束', exact: true }).click()
  await page.getByRole('button', { name: '确认结束', exact: true }).click()
  await expect(page.getByText('会话已结束，最后保存的草稿已归档。')).toBeVisible()
  expect(errors).toEqual([])
})

test('发送冻结点击内容，原生复制及未埋点网页交互保留真实来源', async ({ page }) => {
  captureEvents(page)
  const { tokens } = JSON.parse(
    fs.readFileSync(path.resolve('../artifacts/e2e-current.json'), 'utf8'),
  )
  await page.goto('/enter?seat=02&token=' + tokens['02'])
  await prepareTask(page)
  await page.getByRole('button', { name: '工作台', exact: true }).click()
  const message = page.getByLabel('给 AI 的消息')
  await message.fill('点击时的问题')
  let release!: () => void, entered!: () => void
  const gate = new Promise<void>((resolve) => (release = resolve))
  const arrived = new Promise<void>((resolve) => (entered = resolve))
  let delayed = false
  await page.route('**/api/v1/drafts/*', async (route) => {
    if (!delayed && route.request().method() === 'PUT') {
      delayed = true
      entered()
      await gate
    }
    await route.continue()
  })
  await page.getByRole('button', { name: '发送 ↑', exact: true }).click()
  await arrived
  const afterClick = await page.evaluate(() => Date.now())
  await message.fill('发送后继续写的下一条问题')
  release()
  await expect.poll(async () => (await state(page)).ai_requests.length).toBe(1)
  const request = (await state(page)).ai_requests[0]
  expect(request.command.message_text).toBe('点击时的问题')
  expect(Date.parse(request.command.transport.raw_time)).toBeLessThanOrEqual(afterClick)
  await expect(message).toHaveValue('发送后继续写的下一条问题')
  await expect(page.getByRole('button', { name: '复制代码', exact: true })).toBeVisible()
  const span = page.locator('[data-response-id] [data-offset]').first()
  await span.evaluate((el) => {
    const range = document.createRange()
    range.selectNodeContents(el)
    const selection = getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
  })
  const copyEvent = page.waitForRequest(
    (r) =>
      r.url().endsWith('/events/batch') &&
      r
        .postDataJSON()
        .events.some((e: { event_name: string }) => e.event_name === 'ai_response_copied'),
  )
  await page.keyboard.press('Control+c')
  const copies = (await copyEvent)
    .postDataJSON()
    .events.filter((e: { event_name: string }) => e.event_name === 'ai_response_copied')
  expect(copies).toHaveLength(1)
  expect(copies[0].payload.response_id).toBe(request.response_id)
  expect(copies[0].payload.selection_ranges.length).toBeGreaterThan(0)
  const editor = page.getByTestId('code-input')
  await editor.click()
  await page.keyboard.insertText(
    '<!doctype html><input id="check" type="checkbox"><select id="select"><option>A</option><option>B</option></select><input id="answer"><form id="quiz" onsubmit="event.preventDefault()"><button id="submit">提交</button></form><div id="custom">自定义</div><script>document.getElementById("custom").addEventListener("click",()=>{});</script>',
  )
  await page.getByRole('button', { name: '▶ 运行', exact: true }).click()
  const frame = page.frameLocator('iframe[title="网站预览"]')
  await frame.locator('#check').check()
  await frame.locator('#select').focus()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Tab')
  await frame.locator('#answer').fill('hello')
  await frame.locator('#custom').click()
  await frame.locator('#submit').click()
  await frame.locator('#custom').evaluate((el) => (el as HTMLElement).click())
  await page.getByRole('button', { name: '结束', exact: true }).click()
  await page.getByRole('button', { name: '确认结束', exact: true }).click()
  await expect(page.getByText('会话已结束，最后保存的草稿已归档。')).toBeVisible()
  const interactions = (await state(page)).preview_logs.filter(
    (r: { message: { kind: string } }) => r.message.kind === 'interaction',
  )
  expect(
    interactions
      .map((r: { message: { interaction_type: string } }) => r.message.interaction_type)
      .sort(),
  ).toEqual(['activate', 'change', 'change', 'input_commit', 'submit'].sort())
})
