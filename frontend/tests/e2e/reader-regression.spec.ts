import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { prepareTask } from './onboarding'

test('27页教材在小窗口保留工具栏、双向定位缩略图、正确缩放文字并重置页引用用途', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.setViewportSize({ width: 1280, height: 720 })
  const reviewed = JSON.parse(fs.readFileSync(path.resolve('../config/resources/unit6-fantastic-friends-source-v2.reviewed.json'), 'utf8'))
  await page.route('**/api/v1/tasks/*/resources', async route => {
    const response = await route.fetch()
    const body = await response.json()
    body.resources = body.resources.map((resource: { type: string }) => resource.type === 'textbook' ? {
      ...resource, page_count: 27,
      pages: reviewed.pages.map((item: object) => ({ ...item, ai_input_status: 'ready' })),
    } : resource)
    await route.fulfill({ response, json: body })
  })
  await page.route('**/api/v1/resources/*/versions/*?download=true', route => route.fulfill({
    path: path.resolve('../config/resources/unit6-fantastic-friends-source-v2.pdf'), contentType: 'application/pdf',
  }))
  const { tokens } = JSON.parse(fs.readFileSync(path.resolve('../artifacts/e2e-current.json'), 'utf8'))
  await page.goto('/enter?seat=02&token=' + tokens['02'])
  await prepareTask(page)
  await page.getByRole('button', { name: '教材', exact: true }).click()
  await expect(page.locator('.pdf-page .textLayer span').first()).toBeAttached({ timeout: 30000 })
  await expect(page.locator('.pdf-thumbnails button')).toHaveCount(27)
  const withinViewport = async (selector: string) => page.locator(selector).evaluate(element => {
    const bounds = element.getBoundingClientRect()
    return bounds.top >= 0 && bounds.bottom <= window.innerHeight
  })
  expect(await withinViewport('.reader-controls')).toBe(true)
  expect(await withinViewport('.statusbar')).toBe(true)
  const aligned = async () => page.locator('.pdf-thumbnails').evaluate(list => {
    const item = list.querySelector('[aria-current="page"]')!
    const bounds = list.getBoundingClientRect(), box = item.getBoundingClientRect()
    return box.top >= bounds.top - 1 && box.bottom <= bounds.bottom + 1
  })
  // The first two pages exercise the original OCR layer, not a synthetic PDF.
  for (const index of [1, 2]) {
    await expect.poll(() => page.locator(`[data-pdf-page="${index}"] .textLayer span`).count()).toBeGreaterThan(0)
    const dimensions = await page.locator(`[data-pdf-page="${index}"]`).evaluate(article => {
      const sheet = article.querySelector('.pdf-sheet')!, layer = article.querySelector('.textLayer')!, span = layer.querySelector('span')!
      return { sheet: sheet.getBoundingClientRect().width, layer: layer.getBoundingClientRect().width, font: parseFloat(getComputedStyle(span).fontSize) }
    })
    expect(Math.abs(dimensions.sheet - dimensions.layer)).toBeLessThan(2)
    expect(dimensions.font).toBeGreaterThan(1)
    await page.getByLabel('教材页序').fill(String(index))
    await page.getByLabel('教材页序').press('Enter')
    const firstText = page.locator(`[data-pdf-page="${index}"] .textLayer span`).filter({ hasText: /\S/ }).first()
    await firstText.dblclick()
    await expect.poll(() => page.evaluate(() => window.getSelection()?.toString().trim().length || 0)).toBeGreaterThan(0)
    await page.keyboard.press('Control+C')
    await expect.poll(() => page.evaluate(async () => (await navigator.clipboard.readText()).trim().length)).toBeGreaterThan(0)
  }
  await page.getByLabel('教材页序').fill('20')
  await page.getByLabel('教材页序').press('Enter')
  await expect.poll(aligned).toBe(true)
  await expect(page.locator('.pdf-thumbnails [aria-current="page"]')).toHaveAttribute('data-thumbnail-page', '20')
  // Scrolling the main content updates the current page and brings its thumbnail into view.
  await page.locator('.pdf-scroll').focus()
  await page.locator('.pdf-scroll').evaluate(viewer => {
    viewer.dispatchEvent(new WheelEvent('wheel'))
    const item = viewer.querySelector('[data-pdf-page="26"]')!
    viewer.scrollTop += item.getBoundingClientRect().top - viewer.getBoundingClientRect().top - 20
  })
  await expect(page.getByLabel('教材页序')).toHaveValue('26')
  await expect.poll(aligned).toBe(true)
  await page.locator('[data-thumbnail-page="25"]').click()
  await expect(page.getByLabel('教材页序')).toHaveValue('25')
  await page.getByRole('button', { name: '放大教材' }).click()
  await expect(page.locator('.reader-controls')).toContainText('110%')
  await expect(page.getByLabel('教材页序')).toHaveValue('25')
  await page.getByRole('button', { name: '缩小教材' }).click()
  await expect(page.locator('.reader-controls')).toContainText('100%')
  await page.getByRole('button', { name: '适宽', exact: true }).click()
  await expect.poll(() => page.locator('[data-pdf-page="25"] .pdf-sheet').evaluate(sheet =>
    sheet.getBoundingClientRect().width <= document.querySelector('.pdf-scroll')!.clientWidth - 39,
  )).toBe(true)
  await page.getByLabel('教材页序').fill('1')
  await page.getByLabel('教材页序').press('Enter')
  await expect(page.locator('.reference-options summary')).toContainText('第 1 页')
  await page.locator('.reference-options summary').click()
  await page.getByLabel('引用用途', { exact: true }).selectOption('knowledge_point')
  await page.getByLabel('引用备注').fill('第一页的备注')
  await page.getByRole('button', { name: '下一页', exact: true }).click()
  await expect(page.getByLabel('教材页序')).toHaveValue('2')
  await expect(page.getByLabel('引用用途', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('引用备注')).toHaveValue('')
  await page.getByLabel('引用用途', { exact: true }).selectOption('feedback_design')
  await page.getByLabel('引用备注').fill('第二页的备注')
  await page.getByRole('button', { name: '引用当前页', exact: true }).click()
  await expect(page.getByLabel('引用用途', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('引用备注')).toHaveValue('')
  const state = await page.evaluate(async () => (await fetch('/api/v1/workbench/state', { headers: { Authorization: 'Bearer ' + localStorage.getItem('session-token') } })).json())
  expect(state.resource_references.at(-1)).toMatchObject({ page: 2, reference_purpose: 'feedback_design', reference_note: '第二页的备注' })
  await page.screenshot({ path: '../artifacts/reader-regression-2026-10-13.png' })
  expect(errors).toEqual([])
})
