const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const widths = [320, 360, 375, 390, 430, 768, 1024, 1440];

function watchRuntime(page) {
  const problems = [];
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') {
      problems.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`));
  return problems;
}

async function expectNoOverflow(page) {
  const metrics = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    page: document.documentElement.scrollWidth,
  }));
  expect(metrics.page).toBeLessThanOrEqual(metrics.viewport);
}

async function expectNoSeriousA11yFailures(page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const violations = result.violations.filter((item) => ['serious', 'critical'].includes(item.impact));
  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
}

test('home publishes only verified facts and passes the visual release matrix', async ({ page }, testInfo) => {
  const runtimeProblems = watchRuntime(page);
  for (const width of widths) {
    await page.setViewportSize({ width, height: width <= 430 ? 844 : 900 });
    await page.goto('/');
    await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('.plan-card')).toHaveCount(3);
    await expect(page.locator('.plan-card').nth(0)).toContainText('₹999');
    await expect(page.locator('.plan-card').nth(1)).toContainText('₹1,499');
    await expect(page.locator('.plan-card').nth(2)).toContainText('₹2,499');
    await expect(page.locator('body')).not.toContainText('GST invoice available');
    await expectNoOverflow(page);
    const fixed = await page.locator('body *').evaluateAll((nodes) => nodes
      .filter((node) => getComputedStyle(node).position === 'fixed')
      .map((node) => node.id || node.className));
    expect(fixed.filter((name) => !['site-header', 'header'].includes(String(name))
      && !String(name).includes('skip-link'))).toEqual([]);
    if (width <= 768) {
      await expect(page.locator('#menu-open')).toBeVisible();
    } else {
      await expect(page.locator('.desktop-nav')).toBeVisible();
    }
    await page.screenshot({ path: testInfo.outputPath(`home-${width}.png`), fullPage: true });
  }
  expect(runtimeProblems).toEqual([]);
});

test('visit request validates, submits and returns an authoritative reference', async ({ page }, testInfo) => {
  const runtimeProblems = watchRuntime(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Request a visit' }).first().click();
  await expect(page.locator('#request-dialog')).toBeVisible();
  await expect(page.locator('html')).toHaveClass(/modal-open/);
  await expect(page.locator('#enquiry-type')).toBeFocused();
  await page.locator('#enquiry-name').fill('Gravity QA Visitor');
  await page.locator('#enquiry-phone').fill('98765 43210');
  const preferredDate = await page.locator('#enquiry-date').getAttribute('min');
  await page.locator('#enquiry-date').fill(preferredDate);
  await page.locator('#enquiry-time').selectOption('morning');
  await page.getByRole('button', { name: 'Send request' }).click();
  await expect(page.getByRole('heading', { name: 'Gravity has your request.' })).toBeVisible();
  await expect(page.locator('#enquiry-reference')).toHaveText(/^GF-\d{6}-[A-F0-9]{6}$/);
  await expect(page.locator('#enquiry-whatsapp')).toHaveAttribute('href', /^https:\/\/wa\.me\/917999526112\?text=/);
  await page.screenshot({ path: testInfo.outputPath('request-success-390.png'), fullPage: true });
  expect(runtimeProblems).toEqual([]);
});

test('membership enquiry preserves the selected verified plan', async ({ page }) => {
  await page.goto('/#membership');
  await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
  await page.locator('.plan-card').filter({ hasText: 'Pro' }).getByRole('button').click();
  await expect(page.locator('#enquiry-type')).toHaveValue('membership');
  await expect(page.locator('#enquiry-plan')).toHaveValue(/.+/);
  await expect(page.locator('#enquiry-plan').locator('option:checked')).toContainText('Pro — ₹1,499/month');
  await expect(page.locator('#enquiry-plan')).toHaveAttribute('required', '');
});

test('mobile navigation locks scrolling and restores focus', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/');
  await page.locator('#menu-open').click();
  await expect(page.locator('#mobile-menu')).toBeVisible();
  await expect(page.locator('#menu-open')).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('html')).toHaveClass(/modal-open/);
  await page.locator('#menu-close').click();
  await expect(page.locator('#mobile-menu')).not.toBeVisible();
  await expect(page.locator('#menu-open')).toBeFocused();
  await expect(page.locator('#menu-open')).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('html')).not.toHaveClass(/modal-open/);
});

test('account fails closed without loading external authentication providers', async ({ page }) => {
  const external = [];
  page.on('request', (request) => {
    const host = new URL(request.url()).hostname;
    if (!['127.0.0.1', 'localhost'].includes(host)) external.push(request.url());
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/account');
  await expect(page.locator('#account-unavailable')).toBeVisible();
  await expect(page.locator('#account-checking')).toBeHidden();
  await expect(page.locator('#account-signed-out')).toBeHidden();
  await expectNoOverflow(page);
  expect(external).toEqual([]);
});

test('secondary routes, canonical metadata and privacy review marker are complete', async ({ page }) => {
  const cases = [
    ['/coaching', 'Start with your goal.'],
    ['/gallery', 'Current posts, from the source.'],
    ['/privacy', 'Clear handling of your information.'],
  ];
  for (const [route, heading] of cases) {
    await page.goto(route);
    await expect(page.getByRole('heading', { name: heading, exact: false })).toBeVisible();
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', new RegExp(`${route}$`));
    await expectNoOverflow(page);
  }
  await expect(page.locator('body')).toContainText('REQUIRES_OPERATOR_LEGAL_REVIEW');
  const robots = await (await page.request.get('/robots.txt')).text();
  const sitemap = await (await page.request.get('/sitemap.xml')).text();
  expect(robots).toContain('/sitemap.xml');
  for (const route of ['/', '/coaching', '/gallery', '/privacy']) expect(sitemap).toContain(route);
});

test('public pages have no serious or critical automated accessibility violations', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
  await expectNoSeriousA11yFailures(page);
  await page.getByRole('button', { name: 'Request a visit' }).first().click();
  await expectNoSeriousA11yFailures(page);
  await page.locator('#request-close').click();
  for (const route of ['/coaching', '/gallery', '/privacy', '/account']) {
    await page.goto(route);
    await expectNoSeriousA11yFailures(page);
  }
});
