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
  test.setTimeout(90_000);
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
  await page.goto('/trainers');
  await expect(page.getByRole('heading', { name: 'Start with your goal.', exact: false })).toBeVisible();
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', /\/coaching$/);
  await expectNoOverflow(page);
  const robots = await (await page.request.get('/robots.txt')).text();
  const sitemap = await (await page.request.get('/sitemap.xml')).text();
  expect(robots).toContain('/sitemap.xml');
  for (const route of ['/', '/coaching', '/gallery', '/privacy']) expect(sitemap).toContain(route);
  expect(sitemap).not.toContain('/trainers');
});

test('public pages have no serious or critical automated accessibility violations', async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto('/');
  await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
  await expectNoSeriousA11yFailures(page);
  await page.getByRole('button', { name: 'Request a visit' }).first().click();
  await expectNoSeriousA11yFailures(page);
  await page.locator('#request-close').click();
  for (const route of ['/coaching', '/trainers', '/gallery', '/privacy']) {
    await page.goto(route);
    await expectNoSeriousA11yFailures(page);
  }
});

const publicRoutes = ['/', '/coaching', '/gallery', '/privacy'];
const responsiveRoutes = [...publicRoutes, '/trainers'];

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
  for (const route of responsiveRoutes) {
    await page.setViewportSize({ width: widths[0], height: 844 });
    await page.goto(route);
    if (route === '/') await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
    for (const width of widths) {
      await page.setViewportSize({ width, height: width <= 430 ? 844 : 900 });
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
    await expect(page.locator('meta[property="og:image:alt"]')).toHaveAttribute('content', 'Gravity Fitness Neemuch');
    await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute('content', 'summary_large_image');
    await expect(page.locator('meta[name="twitter:image"]')).toHaveAttribute('content', /\/assets\/og-gravity\.png$/);
    await expect(page.locator('meta[name="twitter:image:alt"]')).toHaveAttribute('content', 'Gravity Fitness Neemuch');
    await expect(page.locator('meta[name="twitter:title"]')).toHaveAttribute('content', /Gravity Fitness/);
    await expect(page.locator('meta[name="twitter:description"]')).toHaveAttribute('content', /.{20,}/);
    await expect(page.locator('link[rel="stylesheet"]')).toHaveAttribute('href', /gravity2-public-ui3/);
    await expect(page.locator('script[src^="/js/public-page.js"]')).toHaveAttribute('src', /gravity2-public-ui4/);
  }
});

test('mobile navigation labels current page and Escape restores the trigger', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await page.goto('/coaching');
  await page.locator('#menu-open').click();
  await expect(page.locator('#mobile-menu')).toBeVisible();
  await expect(page.locator('#mobile-menu nav')).toHaveAttribute('aria-label', 'Mobile navigation');
  await expect(page.locator('#mobile-menu a[aria-current="page"]')).toHaveText(/Coaching/);
  await expect(page.locator('#mobile-menu a[aria-current="page"]')).toHaveAccessibleName('Coaching');
  const menuIndexes = page.locator('#mobile-menu nav a > span');
  await expect(menuIndexes).toHaveCount(5);
  for (let index = 0; index < 5; index += 1) await expect(menuIndexes.nth(index)).toHaveAttribute('aria-hidden', 'true');
  const finalMenuAction = page.locator('#mobile-menu > .button');
  await finalMenuAction.focus();
  await page.keyboard.press('Tab');
  const focusIsTrapped = await page.locator('#mobile-menu').evaluate((menu) => menu.contains(document.activeElement));
  expect(focusIsTrapped).toBe(true);
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

test('membership loading geometry matches the rendered card grid', async ({ page }) => {
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });
    await page.goto('/#membership');
    const plans = page.locator('#public-membership-plans');
    await expect(plans).toHaveAttribute('aria-busy', 'false');
    const metrics = await plans.evaluate((grid) => {
      const gridStyle = getComputedStyle(grid);
      const probe = document.createElement('div');
      probe.className = 'plan-skeleton';
      probe.style.cssText = 'display:block;position:absolute;visibility:hidden;pointer-events:none';
      document.body.appendChild(probe);
      const skeletonHeight = parseFloat(getComputedStyle(probe).minHeight);
      probe.remove();
      const columnCount = gridStyle.gridTemplateColumns.split(' ').filter(Boolean).length;
      const rowCount = Math.ceil(3 / columnCount);
      const rowGap = parseFloat(gridStyle.rowGap);
      return {
        renderedHeight: grid.getBoundingClientRect().height,
        reservedHeight: (skeletonHeight * rowCount) + (rowGap * (rowCount - 1)),
      };
    });
    expect(Math.abs(metrics.renderedHeight - metrics.reservedHeight)).toBeLessThanOrEqual(2);
  }
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


test('public pages keep a valid semantic heading outline and safe external links', async ({ page }) => {
  for (const route of publicRoutes) {
    await page.goto(route);
    await expect(page.locator('main h1')).toHaveCount(1);
    const outline = await page.locator('h1, h2, h3, h4, h5, h6').evaluateAll((nodes) => nodes.map((node) => Number(node.tagName.slice(1))));
    expect(outline[0]).toBe(1);
    for (let index = 1; index < outline.length; index += 1) {
      expect(outline[index] - outline[index - 1], `${route} heading jump at ${index}`).toBeLessThanOrEqual(1);
    }
    const unsafeTargets = await page.locator('a[target="_blank"]').evaluateAll((links) => links.flatMap((link) => {
      const rel = new Set((link.getAttribute('rel') || '').split(/\s+/).filter(Boolean));
      return rel.has('noopener') && rel.has('noreferrer') ? [] : [link.getAttribute('href')];
    }));
    expect(unsafeTargets, `${route} has unsafe new-tab links`).toEqual([]);
  }
});

test('all same-origin public navigation links resolve successfully', async ({ page, request }) => {
  const paths = new Set();
  for (const route of publicRoutes) {
    await page.goto(route);
    const hrefs = await page.locator('a[href]').evaluateAll((links) => links.map((link) => link.getAttribute('href')));
    for (const href of hrefs) {
      if (!href || href.startsWith('#') || /^(?:tel:|mailto:|https?:\/\/)/i.test(href)) continue;
      paths.add(new URL(href, 'http://gravity.local').pathname);
    }
  }
  for (const path of paths) {
    const response = await request.get(path);
    expect(response.status(), `${path} should resolve`).toBeLessThan(400);
  }
});

test('public pages provide a useful no-JavaScript contact fallback', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  try {
    for (const route of publicRoutes) {
      await page.goto(route);
      await expect(page.locator('.noscript-banner')).toBeVisible();
      await expect(page.locator('.noscript-banner a[href^="tel:"]')).toHaveAttribute('href', 'tel:+917999526112');
      await expectNoOverflow(page);
    }
    await page.goto('/');
    await expect(page.locator('#public-membership-plans')).toBeHidden();
    await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
    await expect(page.locator('.membership-noscript')).toBeVisible();
  } finally {
    await context.close();
  }
});

test('membership API failure degrades to a clear contact state', async ({ page }) => {
  await page.route('**/api/membership/plans', (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ error: 'temporarily_unavailable' }),
  }));
  await page.goto('/#membership');
  await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('.plan-card')).toHaveCount(1);
  await expect(page.locator('.plan-card')).toContainText('Prices unavailable');
  await expect(page.locator('.plan-card a[href^="tel:"]')).toHaveAttribute('href', 'tel:+917999526112');
});

test('public controls remain distinguishable in forced-colors mode', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ forcedColors: 'active' });
  await page.goto('/');
  await expect(page.locator('#public-membership-plans')).toHaveAttribute('aria-busy', 'false');
  const button = page.locator('.hero-actions .button').first();
  await expect(button).toBeVisible();
  const styles = await button.evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      forcedColorAdjust: style.forcedColorAdjust,
      borderStyle: style.borderStyle,
      borderWidth: parseFloat(style.borderTopWidth),
    };
  });
  expect(styles.forcedColorAdjust).toBe('auto');
  expect(styles.borderStyle).not.toBe('none');
  expect(styles.borderWidth).toBeGreaterThanOrEqual(1);
});


async function mockSignedInNotificationAccount(page, responder) {
  const user = {
    id: 'customer-notification-test', status: 'active', displayName: 'Gravity Member',
    email: 'member@example.com', emailVerified: true, phone: '+919876543210', phoneVerified: true,
    photoUrl: null, providers: ['password', 'phone'], profileComplete: true, profile: {},
  };
  await page.route('**/api/auth/config', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({
      enabled: true,
      firebase: { apiKey: 'public-test-key', authDomain: 'gravity-authe.firebaseapp.com', projectId: 'gravity-authe', appId: '1:123:web:test' },
    }),
  }));
  await page.route('**/api/auth/session', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ authenticated: true, user }),
  }));
  await page.route('**/api/me/membership', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ membership: { current: null, upcoming: null, history: [] } }),
  }));
  await page.route('**/api/payment/config', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ enabled: false, paymentMode: 'disabled' }),
  }));
  await page.route('**/api/membership/plans', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ plans: [] }),
  }));
  await page.route('**/api/me/payments?limit=25', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ payments: [] }),
  }));
  await page.route('**/api/me/invoices?limit=25', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ invoices: [] }),
  }));
  await page.route('**/api/me/coaching', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ coaching: { latestMeasurements: [], goals: [], currentDiet: null } }),
  }));
  await page.route('**/api/me/notifications', async (route) => {
    const response = typeof responder === 'function' ? responder() : responder;
    await route.fulfill({ contentType: 'application/json', ...response });
  });
}

async function mockNotificationAdmin(page, responder, onScan = null) {
  const admin = { id: 'admin-notification-test', username: 'owner', role: 'owner', permissions: ['notifications.manage'] };
  await page.route('**/api/admin/session', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ configured: true, bootstrapRequired: false, authenticated: true, admin }),
  }));
  await page.route('**/api/admin/dashboard', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ customers: { total: 0, active: 0, disabled: 0 }, admins: { active: 1 }, recentAudit: [] }),
  }));
  await page.route('**/api/admin/notifications?limit=100', async (route) => {
    const response = typeof responder === 'function' ? responder() : responder;
    await route.fulfill({ contentType: 'application/json', ...response });
  });
  await page.route('**/api/admin/notifications/scan', async (route) => {
    if (onScan) onScan(route.request().postDataJSON());
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ scan: { created: 0, deduped: 0, suppressedRenewed: 0 } }) });
  });
}

function notificationFixture() {
  const now = Math.floor(Date.now() / 1000);
  return [
    {
      id: 'reminder-internal-7', eventType: 'membership_expiry', customerId: 'customer-internal-1', membershipId: 'membership-internal-1',
      triggerDays: 7, state: 'pending', customer: { displayName: 'Asha Member' },
      payload: { planName: 'Pro', membershipNumber: 'GF-M-1001', endsAt: now + 7 * 86400 },
      deliveries: [
        { id: 'delivery-internal-1', recipientRole: 'customer', channel: 'email', status: 'sent', lastErrorCode: null },
        { id: 'delivery-internal-2', recipientRole: 'customer', channel: 'sms', status: 'queued' },
        { id: 'delivery-internal-3', recipientRole: 'customer', channel: 'whatsapp', status: 'blocked_external_config' },
        { id: 'delivery-internal-4', recipientRole: 'owner', channel: 'email', status: 'sent' },
        { id: 'delivery-internal-5', recipientRole: 'owner', channel: 'sms', status: 'failed', nextAttemptAt: now + 3600, lastErrorCode: 'sms_delivery_failed' },
        { id: 'delivery-internal-6', recipientRole: 'owner', channel: 'whatsapp', status: 'missing_recipient' },
      ],
    },
    {
      id: 'reminder-internal-0', eventType: 'membership_expiry', customerId: 'customer-internal-2', membershipId: 'membership-internal-2',
      triggerDays: 0, state: 'pending', customer: { displayName: 'Ravi Member' },
      payload: { planName: 'Basic', membershipNumber: 'GF-M-1002', endsAt: now - 1800 },
      deliveries: [
        { recipientRole: 'customer', channel: 'email', status: 'failed', nextAttemptAt: null, lastErrorCode: 'smtp_delivery_failed' },
        { recipientRole: 'customer', channel: 'sms', status: 'missing_recipient' },
        { recipientRole: 'customer', channel: 'whatsapp', status: 'queued' },
        { recipientRole: 'owner', channel: 'email', status: 'blocked_external_config' },
        { recipientRole: 'owner', channel: 'sms', status: 'sent' },
      ],
    },
    {
      id: 'reminder-internal-suppressed', eventType: 'membership_expiry', customerId: 'customer-internal-3', membershipId: 'membership-internal-3',
      triggerDays: 3, state: 'suppressed', customer: { displayName: 'Renewed Member' },
      payload: { planName: 'Elite', membershipNumber: 'GF-M-1003', endsAt: now + 3 * 86400 },
      deliveries: [
        { recipientRole: 'customer', channel: 'email', status: 'sent' },
        { recipientRole: 'customer', channel: 'sms', status: 'queued' },
        { recipientRole: 'customer', channel: 'whatsapp', status: 'blocked_external_config' },
        { recipientRole: 'owner', channel: 'email', status: 'queued' },
        { recipientRole: 'owner', channel: 'sms', status: 'queued' },
        { recipientRole: 'owner', channel: 'whatsapp', status: 'queued' },
      ],
    },
  ];
}

test('customer membership expiry reminder history is clear and privacy-safe', async ({ page }, testInfo) => {
  const runtimeProblems = watchRuntime(page);
  const now = Math.floor(Date.now() / 1000);
  const reminders = [7, 3, 1, 0].map((triggerDays, index) => ({
    id: `customer-reminder-${index}`, eventType: 'membership_expiry', triggerDays,
    state: 'pending', payload: { planName: index === 0 ? 'Pro' : 'Basic', membershipNumber: `GF-M-${index}`, endsAt: now + triggerDays * 86400 },
    deliveries: [{ id: `private-delivery-${index}`, recipientRole: 'customer', channel: 'email', status: index ? 'queued' : 'sent', lastErrorCode: 'private_provider_error' }],
  }));
  reminders.push({
    id: 'customer-reminder-suppressed', eventType: 'membership_expiry', triggerDays: 3, state: 'suppressed',
    payload: { planName: 'Elite', membershipNumber: 'GF-M-RENEW', endsAt: now + 3 * 86400 },
    deliveries: [{ id: 'private-delivery-suppressed', recipientRole: 'customer', channel: 'whatsapp', status: 'blocked_external_config' }],
  });
  await mockSignedInNotificationAccount(page, { status: 200, body: JSON.stringify({ notifications: reminders }) });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/account');
  const card = page.locator('#notification-history-card');
  await expect(card).toBeVisible();
  await expect(card.getByText('Membership expiry', { exact: true })).toHaveCount(5);
  await expect(card).toContainText('7 days');
  await expect(card).toContainText('3 days');
  await expect(card).toContainText('1 day');
  await expect(card).toContainText('Expired today');
  await expect(card).toContainText('Renewal confirmed. This reminder was stopped.');
  await expect(card).toContainText('Pro');
  const factValues = await card.locator('.notification-reminder-facts dd').allTextContents();
  expect(factValues).not.toContain('Not available');
  const privateText = await card.innerText();
  for (const forbidden of ['SMS', 'WhatsApp', 'blocked_external_config', 'private_provider_error', 'private-delivery', 'recipientRole', 'attemptCount']) {
    expect(privateText).not.toContain(forbidden);
  }
  await expectNoSeriousA11yFailures(page);
  await page.screenshot({ path: testInfo.outputPath('customer-reminders-390.png'), fullPage: true });
  for (const width of widths) {
    await page.setViewportSize({ width, height: width <= 430 ? 844 : 900 });
    await expectNoOverflow(page);
  }
  expect(runtimeProblems).toEqual([]);
});

test('customer reminder history handles empty and unavailable states', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  let mode = 'empty';
  await mockSignedInNotificationAccount(page, () => mode === 'empty'
    ? { status: 200, body: JSON.stringify({ notifications: [] }) }
    : { status: 503, body: JSON.stringify({ error: 'provider_raw_error_should_not_render' }) });
  await page.goto('/account');
  await expect(page.locator('#notification-history-list')).toHaveText('No membership reminders yet.');
  expect(runtimeProblems).toEqual([]);
  mode = 'error';
  await page.reload();
  await expect(page.locator('#notification-history-list')).toContainText('Reminder history is temporarily unavailable. Try again later.');
  await expect(page.locator('#notification-history-card')).not.toContainText('provider_raw_error_should_not_render');
  expect(runtimeProblems.filter((problem) => !problem.includes('503 (Service Unavailable)'))).toEqual([]);
});

test('admin expiry notifications separate customer and owner delivery truthfully', async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const runtimeProblems = watchRuntime(page);
  const notifications = notificationFixture();
  let scanBody = null;
  const response = {
    status: 200,
    body: JSON.stringify({
      notifications,
      providerBlockers: { email: 'READY', sms: 'BLOCKED_ADAPTER_MISSING', whatsapp: 'BLOCKED_EXTERNAL_CONFIG' },
    }),
  };
  await mockNotificationAdmin(page, response, (body) => { scanBody = body; });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/admin');
  await expect(page.locator('#app')).toBeVisible();
  await page.locator('#notificationsNav').click();
  await expect(page.locator('#notificationsList')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('.notification-admin-card')).toHaveCount(3);

  const asha = page.locator('.notification-admin-card').filter({ hasText: 'Asha Member' });
  const ashaCustomer = asha.locator('.notification-audience').filter({ hasText: 'Customer notifications' });
  const ashaOwner = asha.locator('.notification-audience').filter({ hasText: 'Owner notifications' });
  await expect(ashaCustomer.getByLabel('Email: Sent')).toBeVisible();
  await expect(ashaCustomer.getByLabel('SMS: Queued')).toBeVisible();
  await expect(ashaCustomer.getByLabel('WhatsApp: Blocked by configuration')).toBeVisible();
  await expect(ashaOwner.getByLabel('Email: Sent')).toBeVisible();
  await expect(ashaOwner.getByLabel('SMS: Retrying')).toBeVisible();
  await expect(ashaOwner.getByLabel('WhatsApp: Missing recipient')).toBeVisible();

  const ravi = page.locator('.notification-admin-card').filter({ hasText: 'Ravi Member' });
  await expect(ravi).toContainText('Expired today');
  await expect(ravi.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('Email: Failed')).toBeVisible();
  await expect(ravi.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('SMS: Missing recipient')).toBeVisible();
  await expect(ravi.locator('.notification-audience').filter({ hasText: 'Owner notifications' }).getByLabel('Email: Blocked by configuration')).toBeVisible();
  await expect(ravi.locator('.notification-audience').filter({ hasText: 'Owner notifications' }).getByLabel('WhatsApp: Status unavailable')).toBeVisible();

  const renewed = page.locator('.notification-admin-card').filter({ hasText: 'Renewed Member' });
  await expect(renewed).toContainText('Suppressed after renewal');
  await expect(renewed.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('Email: Sent')).toBeVisible();
  await expect(renewed.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('SMS: Suppressed after renewal')).toBeVisible();
  await expect(renewed.locator('.notification-audience').filter({ hasText: 'Owner notifications' }).getByLabel('WhatsApp: Suppressed after renewal')).toBeVisible();

  await expect(page.getByLabel('Email provider: Ready')).toBeVisible();
  await expect(page.getByLabel('SMS provider: Blocked by configuration')).toBeVisible();
  await expect(page.getByLabel('WhatsApp provider: Blocked by configuration')).toBeVisible();
  const workspaceText = await page.locator('#notificationsView').innerText();
  for (const forbidden of ['delivery-internal', 'customer-internal', 'membership-internal', 'sms_delivery_failed', 'smtp_delivery_failed', 'BLOCKED_ADAPTER_MISSING', 'BLOCKED_EXTERNAL_CONFIG']) {
    expect(workspaceText).not.toContain(forbidden);
  }

  const filter = page.locator('#notificationFilter');
  await filter.selectOption('expiring');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('1 of 3 reminders shown');
  await filter.selectOption('expired');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('1 of 3 reminders shown');
  await filter.selectOption('failed');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('2 of 3 reminders shown');
  await filter.selectOption('blocked');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('3 of 3 reminders shown');
  await filter.selectOption('suppressed');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('1 of 3 reminders shown');
  await filter.focus();
  await expect(filter).toBeFocused();
  await page.keyboard.press('Home');
  await page.keyboard.press('End');
  await page.keyboard.press('Tab');
  await expect(filter).toHaveValue('suppressed');

  await page.locator('#notificationDays').selectOption('0');
  await page.locator('#scanNotifications').click();
  await expect.poll(() => scanBody).toEqual({ daysBefore: 0 });
  await expectNoSeriousA11yFailures(page);
  await page.screenshot({ path: testInfo.outputPath('admin-reminders-390.png'), fullPage: true });

  await filter.selectOption('all');
  for (const width of widths) {
    await page.setViewportSize({ width, height: width <= 430 ? 844 : 900 });
    await expectNoOverflow(page);
    if (width <= 430) {
      for (const control of ['#notificationDays', '#scanNotifications', '#notificationFilter']) {
        const box = await page.locator(control).boundingBox();
        expect(box.height, `${control} touch target at ${width}`).toBeGreaterThanOrEqual(44);
      }
    }
  }
  expect(runtimeProblems).toEqual([]);
});

test('admin notifications handle all providers blocked, empty data and API failure', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  let mode = 'empty';
  await mockNotificationAdmin(page, () => mode === 'empty'
    ? {
      status: 200,
      body: JSON.stringify({
        notifications: [],
        providerBlockers: { email: 'BLOCKED_EXTERNAL_CONFIG', sms: 'BLOCKED_ADAPTER_MISSING', whatsapp: 'BLOCKED_EXTERNAL_CONFIG' },
      }),
    }
    : { status: 503, body: JSON.stringify({ error: 'raw_backend_error_should_not_render' }) });
  await page.goto('/admin');
  await page.locator('#notificationsNav').click();
  await expect(page.locator('.notification-provider--blocked')).toHaveCount(3);
  await expect(page.locator('#notificationsList')).toHaveText('No membership expiry reminders yet.');
  await expect(page.locator('#notificationsView')).not.toContainText('BLOCKED_EXTERNAL_CONFIG');
  await expect(page.locator('#notificationsView')).not.toContainText('BLOCKED_ADAPTER_MISSING');
  expect(runtimeProblems).toEqual([]);
  mode = 'error';
  await page.evaluate(() => window.GravityNotificationAdmin.renderWorkspace());
  await expect(page.locator('#notificationsList')).toContainText('Notification data is temporarily unavailable. Try again later.');
  await expect(page.locator('#notificationsView')).not.toContainText('raw_backend_error_should_not_render');
  expect(runtimeProblems.filter((problem) => !problem.includes('503 (Service Unavailable)'))).toEqual([]);
});
