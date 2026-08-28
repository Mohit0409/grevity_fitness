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

test('signed-in account exposes explicit verified identity linking without eager provider loading', async ({ page }) => {
  const external = [];
  let sessionUser = {
    id: 'customer-email', status: 'active', displayName: 'Gravity Member',
    email: 'member@example.com', emailVerified: true, phone: null, phoneVerified: false,
    photoUrl: null, providers: ['password'], profileComplete: true, profile: {},
  };
  page.on('request', (request) => {
    const host = new URL(request.url()).hostname;
    if (!['127.0.0.1', 'localhost'].includes(host)) external.push(request.url());
  });
  await page.route('**/api/auth/config', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({
      enabled: true,
      firebase: {
        apiKey: 'public-test-key', authDomain: 'gravity-authe.firebaseapp.com',
        projectId: 'gravity-authe', appId: '1:123:web:test',
      },
    }),
  }));
  await page.route('**/api/auth/session', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ authenticated: true, user: sessionUser }),
  }));
  await page.route('**/api/me/membership', (route) => route.fulfill({
    status: 200, contentType: 'application/json',
    body: JSON.stringify({ membership: { current: null, upcoming: null, history: [] } }),
  }));

  await page.goto('/account');
  await expect(page.locator('#account-signed-in')).toBeVisible();
  await expect(page.locator('#security-provider-count')).toHaveText('1 method');
  await expect(page.locator('#security-provider-summary')).toContainText('Email/password');
  await expect(page.locator('#link-google')).toBeHidden();
  await expect(page.locator('#link-phone-toggle')).toBeVisible();

  sessionUser = {
    ...sessionUser, id: 'customer-phone', email: null, emailVerified: false,
    phone: '+919876543210', phoneVerified: true, providers: ['phone'],
  };
  await page.reload();
  await expect(page.locator('#security-provider-summary')).toContainText('Mobile OTP');
  await expect(page.locator('#link-google')).toBeVisible();
  await expect(page.locator('#link-google')).toHaveText('Add verified Google email');
  await expect(page.locator('#link-phone-toggle')).toBeHidden();
  expect(external).toEqual([]);
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

const publicRoutes = ['/', '/coaching', '/gallery', '/privacy'];

async function expectTouchTargets(page) {
  const failures = await page.locator('a, button, summary, input, select, textarea').evaluateAll((nodes) => nodes.flatMap((node) => {
    if (node.classList.contains('skip-link')) return [];
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden' || rect.width === 0 || rect.height === 0) return [];
    if (rect.width >= 44 && rect.height >= 44) return [];
    return [{
      element: node.tagName.toLowerCase(),
      copy: (node.textContent || node.getAttribute('aria-label') || '').trim().slice(0, 50),
      width: Math.round(rect.width * 10) / 10,
      height: Math.round(rect.height * 10) / 10,
    }];
  }));
  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
}

test('all public routes pass the complete responsive width matrix', async ({ page }) => {
  test.setTimeout(90_000);
  const runtimeProblems = watchRuntime(page);
  for (const route of publicRoutes) {
    for (const width of widths) {
      await page.setViewportSize({ width, height: width <= 430 ? 844 : 900 });
      await page.goto(route);
      if (route === '/') await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
      await expectNoOverflow(page);
      if (width <= 980) {
        await expect(page.locator('#menu-open')).toBeVisible();
        await expect(page.locator('.desktop-nav')).toBeHidden();
      } else {
        await expect(page.locator('#menu-open')).toBeHidden();
        await expect(page.locator('.desktop-nav')).toBeVisible();
      }
      if (width <= 768) await expectTouchTargets(page);
    }
  }
  expect(runtimeProblems).toEqual([]);
});

test('mobile public layouts stay compact without sacrificing tap targets', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/');
  await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
  const compact = await page.evaluate(() => ({
    heroHeading: parseFloat(getComputedStyle(document.querySelector('.hero h1')).fontSize),
    heroArt: document.querySelector('.hero-art').getBoundingClientRect().height,
    sectionPadding: parseFloat(getComputedStyle(document.querySelector('#training')).paddingTop),
    pathMinHeight: getComputedStyle(document.querySelector('.path-card')).minHeight,
    blur: getComputedStyle(document.querySelector('.site-header')).backdropFilter,
  }));
  expect(compact.heroHeading).toBeLessThanOrEqual(60);
  expect(compact.heroArt).toBeLessThanOrEqual(302);
  expect(compact.sectionPadding).toBe(60);
  expect(compact.pathMinHeight).toBe('0px');
  expect(compact.blur).toBe('none');
  await expectTouchTargets(page);
});
test('public metadata is complete and consistent on every indexable route', async ({ page }) => {
  for (const route of publicRoutes) {
    await page.goto(route);
    await expect(page.locator('meta[name="description"]')).toHaveAttribute('content', /.{20,}/);
    await expect(page.locator('meta[property="og:type"]')).toHaveAttribute('content', 'website');
    await expect(page.locator('meta[property="og:locale"]')).toHaveAttribute('content', 'en_IN');
    await expect(page.locator('meta[property="og:site_name"]')).toHaveAttribute('content', 'Gravity Fitness');
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', /Gravity Fitness/);
    await expect(page.locator('meta[property="og:description"]')).toHaveAttribute('content', /.{20,}/);
    await expect(page.locator('meta[property="og:url"]')).toHaveAttribute('content', new RegExp(`${route === '/' ? '/$' : `${route}$`}`));
    await expect(page.locator('meta[property="og:image"]')).toHaveAttribute('content', /\/assets\/og-gravity\.png$/);
    await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute('content', 'summary_large_image');
    await expect(page.locator('meta[name="twitter:title"]')).toHaveAttribute('content', /Gravity Fitness/);
    await expect(page.locator('meta[name="twitter:description"]')).toHaveAttribute('content', /.{20,}/);
    await expect(page.locator('link[rel="stylesheet"]')).toHaveAttribute('href', /gravity2-public-ui2/);
  }
});

test('mobile navigation labels current page and Escape restores the trigger', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/coaching');
  await page.locator('#menu-open').click();
  await expect(page.locator('#mobile-menu')).toBeVisible();
  await expect(page.locator('#mobile-menu nav')).toHaveAttribute('aria-label', 'Mobile navigation');
  await expect(page.locator('#mobile-menu a[aria-current="page"]')).toHaveText(/Coaching/);
  const menuMetrics = await page.locator('#mobile-menu').evaluate((node) => ({
    clientHeight: node.clientHeight,
    scrollHeight: node.scrollHeight,
  }));
  expect(menuMetrics.scrollHeight).toBeLessThanOrEqual(menuMetrics.clientHeight + 80);
  await page.keyboard.press('Escape');
  await expect(page.locator('#mobile-menu')).not.toBeVisible();
  await expect(page.locator('#menu-open')).toBeFocused();
  await expect(page.locator('#menu-open')).toHaveAttribute('aria-expanded', 'false');
  await expect(page.locator('html')).not.toHaveClass(/modal-open/);
});

test('public startup bundle stays lean and makes no third-party startup requests', async ({ page }) => {
  const external = [];
  page.on('request', (request) => {
    const host = new URL(request.url()).hostname;
    if (!['127.0.0.1', 'localhost'].includes(host)) external.push(request.url());
  });
  await page.goto('/');
  await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
  const startupAssets = await page.locator('link[rel="stylesheet"], script[src]').evaluateAll((nodes) =>
    nodes.map((node) => node.getAttribute('href') || node.getAttribute('src')).filter(Boolean));
  expect(startupAssets).toHaveLength(4);
  let rawBytes = (await (await page.request.get('/')).body()).length;
  for (const asset of startupAssets) {
    const response = await page.request.get(asset);
    expect(response.ok(), asset).toBeTruthy();
    rawBytes += (await response.body()).length;
  }
  expect(rawBytes).toBeLessThanOrEqual(64 * 1024);
  expect(external).toEqual([]);
});

test('keyboard-only public flow exposes skip, FAQ and enquiry controls', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto('/');
  await page.keyboard.press('Tab');
  await expect(page.locator('.skip-link')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#main-content$/);
  const firstFaq = page.locator('.faq-list details').first();
  const summary = firstFaq.locator('summary');
  await summary.focus();
  await page.keyboard.press('Enter');
  await expect(firstFaq).toHaveAttribute('open', '');

  const request = page.getByRole('button', { name: 'Request a visit' }).first();
  await request.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('#request-dialog')).toBeVisible();
  await expect(page.locator('#enquiry-type')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.locator('#request-dialog')).not.toBeVisible();
  await expect(request).toBeFocused();
});

test('reduced motion removes continuous public animation and smooth scrolling', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  const motion = await page.evaluate(() => {
    const probe = document.createElement('div');
    probe.className = 'plan-skeleton';
    document.body.appendChild(probe);
    const animationName = getComputedStyle(probe, '::after').animationName;
    probe.remove();
    return {
      scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
      transitionDuration: getComputedStyle(document.querySelector('.button')).transitionDuration,
      animationName,
    };
  });
  expect(motion.scrollBehavior).toBe('auto');
  expect(motion.animationName).toBe('none');
  expect(parseFloat(motion.transitionDuration)).toBeLessThanOrEqual(0.001);
});

test('public routes tolerate 200 percent text resizing without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  for (const route of publicRoutes) {
    await page.goto(route);
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    await expectNoOverflow(page);
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('h1')).toBeVisible();
  }
});
