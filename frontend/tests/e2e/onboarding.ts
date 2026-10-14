import { expect, type Page } from '@playwright/test'
export async function prepareTask(page: Page) {
  await page.getByRole('button', { name: /^(进入任务|继续任务)$/ }).click()
  await expect(
    page
      .getByRole('heading', { name: '开始前的背景信息' })
      .or(page.getByRole('button', { name: '工作台', exact: true })),
  ).toBeVisible()
  if (
    await page
      .getByRole('heading', { name: '开始前的背景信息' })
      .isVisible()
      .catch(() => false)
  ) {
    for (const id of ['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
      await page.locator(`input[name="${id}"]`).first().check()
    await page.getByRole('button', { name: '提交并查看任务' }).click()
  }
  await expect(page.getByRole('button', { name: '工作台', exact: true })).toBeEnabled()
}
