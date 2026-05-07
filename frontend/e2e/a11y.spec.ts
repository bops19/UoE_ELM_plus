import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('a11y: shell page has no critical accessibility violations', async ({ page }) => {
  await page.goto('/app/');

  const results = await new AxeBuilder({ page }).analyze();
  const criticalViolations = results.violations.filter((violation) => violation.impact === 'critical');

  expect(
    criticalViolations,
    criticalViolations.map((violation) => `${violation.id}: ${violation.help}`).join('\n'),
  ).toEqual([]);
});
