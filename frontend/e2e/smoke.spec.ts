import { expect, test } from '@playwright/test';

test('smoke: app shell loads and message composer is interactive', async ({ page }) => {
  await page.goto('/app/');

  await expect(page.getByText('ELM+')).toBeVisible();
  const composer = page.locator('textarea[name="message"]').first();
  await expect(composer).toBeVisible();

  await composer.fill('playwright smoke');
  await expect(composer).toHaveValue('playwright smoke');

  const submitButton = page.locator('button.composer-submit-inside').first();
  await expect(submitButton).toBeEnabled();
  await submitButton.click();

  await expect(composer).toHaveValue('');
});
