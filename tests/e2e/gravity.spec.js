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
  const metrics = await page.evaluate(() => {
    const viewport = document.documentElement.clientWidth;
    const overflowers = Array.from(document.body.querySelectorAll('*')).map((node) => {
      const rect = node.getBoundingClientRect();
      return { node, rect };
    }).filter(({ node, rect }) => rect.width > 0 && rect.right > viewport + 1 && getComputedStyle(node).display !== 'none')
      .slice(0, 8).map(({ node, rect }) => ({
        tag: node.tagName,
        id: node.id,
        className: String(node.className || ''),
        right: Math.round(rect.right),
        width: Math.round(rect.width),
        text: String(node.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80),
      }));
    return { viewport, page: document.documentElement.scrollWidth, overflowers };
  });
  expect(metrics.page, JSON.stringify(metrics.overflowers, null, 2)).toBeLessThanOrEqual(metrics.viewport);
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
  await page.route('**/api/admin/members?q=*', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ members: [] }),
  }));
  await page.route('**/api/admin/memberships/expiring?days=7', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ memberships: [] }),
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
      id: 'reminder-internal-3', eventType: 'membership_expiry', customerId: 'customer-internal-4', membershipId: 'membership-internal-4',
      triggerDays: 3, state: 'pending', customer: { displayName: 'Neha Member' },
      payload: { planName: 'Basic', membershipNumber: 'GF-M-1004', endsAt: now + 3 * 86400 },
      deliveries: [
        { recipientRole: 'customer', channel: 'email', status: 'missing_recipient' },
        { recipientRole: 'customer', channel: 'sms', status: 'missing_recipient' },
        { recipientRole: 'customer', channel: 'whatsapp', status: 'missing_recipient' },
        { recipientRole: 'owner', channel: 'email', status: 'missing_recipient' },
        { recipientRole: 'owner', channel: 'sms', status: 'missing_recipient' },
        { recipientRole: 'owner', channel: 'whatsapp', status: 'missing_recipient' },
      ],
    },
    {
      id: 'reminder-internal-1', eventType: 'membership_expiry', customerId: 'customer-internal-5', membershipId: 'membership-internal-5',
      triggerDays: 1, state: 'pending', customer: { displayName: 'Ishan Member' },
      payload: { planName: null, membershipNumber: null, endsAt: 'not-a-date' },
      deliveries: [
        { recipientRole: 'customer', channel: 'email', status: 'queued' },
        { recipientRole: 'customer', channel: 'sms', status: 'queued' },
        { recipientRole: 'customer', channel: 'whatsapp', status: 'queued' },
        { recipientRole: 'owner', channel: 'email', status: 'queued' },
        { recipientRole: 'owner', channel: 'sms', status: 'queued' },
        { recipientRole: 'owner', channel: 'whatsapp', status: 'queued' },
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
    deliveries: [
      { id: `private-delivery-${index}`, recipientRole: 'customer', channel: 'email', status: index ? 'queued' : 'sent', lastErrorCode: 'private_provider_error' },
      ...(index === 0 ? [{ id: 'owner-hidden-delivery', recipientRole: 'owner', channel: 'email', status: 'failed', lastErrorCode: 'owner_secret_error' }] : []),
    ],
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
  await expect(card).toContainText('Membership expires in 7 days');
  await expect(card).toContainText('Membership expires in 3 days');
  await expect(card).toContainText('Membership expires tomorrow');
  await expect(card).toContainText('Membership expired today');
  await expect(card).toContainText('Renewal confirmed. This reminder was stopped.');
  await expect(card).toContainText('GF-M-0');
  await expect(card).toContainText('Pro');
  await expect(card.getByLabel('Reminder status: Sent')).toHaveCount(1);
  await expect(card.getByLabel('Reminder status: Pending')).toHaveCount(3);
  await expect(card.getByLabel('Reminder status: Suppressed after renewal')).toHaveCount(1);
  const factValues = await card.locator('.notification-reminder-facts dd').allTextContents();
  expect(factValues).not.toContain('Not available');
  const privateText = await card.innerText();
  for (const forbidden of ['SMS', 'WhatsApp', 'blocked_external_config', 'private_provider_error', 'owner_secret_error', 'private-delivery', 'owner-hidden-delivery', 'recipientRole', 'attemptCount']) {
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
  if (await page.locator('#sidebarOpen').isVisible()) await page.locator('#sidebarOpen').click();
  await page.locator('#notificationsNav').click();
  await expect(page.locator('#notificationsList')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('.notification-admin-card')).toHaveCount(5);

  const asha = page.locator('.notification-admin-card').filter({ hasText: 'Asha Member' });
  const ashaCustomer = asha.locator('.notification-audience').filter({ hasText: 'Customer notifications' });
  const ashaOwner = asha.locator('.notification-audience').filter({ hasText: 'Owner notifications' });
  await expect(ashaCustomer.getByLabel('Email: Sent')).toBeVisible();
  await expect(ashaCustomer.getByLabel('SMS: Queued')).toBeVisible();
  await expect(ashaCustomer.getByLabel('WhatsApp: Configuration required')).toBeVisible();
  await expect(ashaOwner.getByLabel('Email: Sent')).toBeVisible();
  await expect(ashaOwner.getByLabel('SMS: Retrying')).toBeVisible();
  await expect(ashaOwner.getByLabel('WhatsApp: Missing recipient')).toBeVisible();

  const ravi = page.locator('.notification-admin-card').filter({ hasText: 'Ravi Member' });
  await expect(ravi).toContainText('Expired today');
  await expect(ravi.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('Email: Failed')).toBeVisible();
  await expect(ravi.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('SMS: Missing recipient')).toBeVisible();
  await expect(ravi.locator('.notification-audience').filter({ hasText: 'Owner notifications' }).getByLabel('Email: Configuration required')).toBeVisible();
  await expect(ravi.locator('.notification-audience').filter({ hasText: 'Owner notifications' }).getByLabel('WhatsApp: Status unavailable')).toBeVisible();

  const neha = page.locator('.notification-admin-card').filter({ hasText: 'Neha Member' });
  await expect(neha.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('Email: Missing recipient')).toBeVisible();
  await expect(neha.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('SMS: Missing recipient')).toBeVisible();
  await expect(neha.locator('.notification-audience').filter({ hasText: 'Owner notifications' }).getByLabel('Email: Missing recipient')).toBeVisible();
  await expect(neha.locator('.notification-audience').filter({ hasText: 'Owner notifications' }).getByLabel('SMS: Missing recipient')).toBeVisible();

  const ishan = page.locator('.notification-admin-card').filter({ hasText: 'Ishan Member' });
  await expect(ishan).toContainText('Membership number unavailable');
  await expect(ishan).toContainText('Not available');

  const renewed = page.locator('.notification-admin-card').filter({ hasText: 'Renewed Member' });
  await expect(renewed).toContainText('Suppressed after renewal');
  await expect(renewed.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('Email: Sent')).toBeVisible();
  await expect(renewed.locator('.notification-audience').filter({ hasText: 'Customer notifications' }).getByLabel('SMS: Suppressed after renewal')).toBeVisible();
  await expect(renewed.locator('.notification-audience').filter({ hasText: 'Owner notifications' }).getByLabel('WhatsApp: Suppressed after renewal')).toBeVisible();

  await expect(page.getByLabel('Email provider: Ready')).toBeVisible();
  await expect(page.getByLabel('SMS provider: Configuration required')).toBeVisible();
  await expect(page.getByLabel('WhatsApp provider: Configuration required')).toBeVisible();
  const workspaceText = await page.locator('#notificationsView').innerText();
  for (const forbidden of ['delivery-internal', 'customer-internal', 'membership-internal', 'sms_delivery_failed', 'smtp_delivery_failed', 'BLOCKED_ADAPTER_MISSING', 'BLOCKED_EXTERNAL_CONFIG']) {
    expect(workspaceText).not.toContain(forbidden);
  }

  const filter = page.locator('#notificationFilter');
  await filter.selectOption('window7');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('1 of 5 reminders shown');
  await filter.selectOption('window3');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('1 of 5 reminders shown');
  await filter.selectOption('window1');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('1 of 5 reminders shown');
  await filter.selectOption('expired');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('1 of 5 reminders shown');
  await filter.selectOption('failed');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('2 of 5 reminders shown');
  await filter.selectOption('blocked');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('3 of 5 reminders shown');
  await filter.selectOption('missing');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('3 of 5 reminders shown');
  await filter.selectOption('suppressed');
  await expect(page.locator('#notificationFilterSummary')).toHaveText('1 of 5 reminders shown');
  await filter.focus();
  await expect(filter).toBeFocused();
  await page.keyboard.press('Home');
  await page.keyboard.press('End');
  await page.keyboard.press('Tab');
  await expect(filter).toHaveValue('suppressed');

  await page.locator('#notificationDays').selectOption('0');
  await page.locator('#scanNotifications').click();
  await expect.poll(() => scanBody).toEqual({ daysBefore: 0 });
  await filter.selectOption('all');
  await filter.focus();
  const focusStyle = await filter.evaluate((node) => ({ style: getComputedStyle(node).outlineStyle, width: parseFloat(getComputedStyle(node).outlineWidth) }));
  expect(focusStyle.style).not.toBe('none');
  expect(focusStyle.width).toBeGreaterThanOrEqual(2);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const motion = await asha.evaluate((node) => ({ animation: getComputedStyle(node).animationName, transition: getComputedStyle(node).transitionDuration }));
  expect(motion.animation).toBe('none');
  expect(motion.transition).toBe('0s');
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
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
  await expectNoOverflow(page);
  await expect(page.locator('#notificationsList')).toBeVisible();
  await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
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


async function mockAdminSoftware(page, options = {}) {
  const now = Math.floor(Date.now() / 1000);
  const day = 86400;
  const admin = { id: 'owner-ui-test', username: 'owner', role: 'owner', permissions: ['*'] };
  const authState = { authenticated: !options.startUnauthenticated };
  const plans = [
    { id: 'plan-basic', code: 'basic', name: 'Basic', pricePaise: 99900, currency: 'INR', durationMonths: 1, status: 'active', sortOrder: 1 },
    { id: 'plan-pro', code: 'pro', name: 'Pro', pricePaise: 149900, currency: 'INR', durationMonths: 3, status: 'active', sortOrder: 2 },
  ];
  const customers = [
    { id: 'cust-asha', displayName: 'Asha Sharma', phone: '+919876543210', phoneVerified: true, email: 'asha@example.com', status: 'active', createdAt: now - 200 * day, lastLoginAt: now - 3600 },
    { id: 'cust-ravi', displayName: 'Ravi Patel', phone: '+919812345678', phoneVerified: true, email: null, status: 'active', createdAt: now - 20 * day, lastLoginAt: null },
    { id: 'cust-disabled', displayName: 'Disabled Member', phone: '+919800001111', phoneVerified: false, email: null, status: 'disabled', createdAt: now - 300 * day, lastLoginAt: null },
  ];
  const memberships = {
    'cust-asha': [
      { id: 'mem-asha-live', membershipNumber: 'GF-2026-ASHA', customerId: 'cust-asha', planId: 'plan-pro', planName: 'Pro', pricePaise: 149900, currency: 'INR', durationMonths: 3, status: 'active', startsAt: now - 60 * day, endsAt: now + 7 * day, daysRemaining: 7, source: 'admin_manual', createdAt: now - 60 * day, payment: { totalPaise: 149900, paidPaise: 50000, pendingPaise: 99900 } },
      { id: 'mem-asha-old', membershipNumber: 'GF-2026-OLD', customerId: 'cust-asha', planId: 'plan-basic', planName: 'Basic', pricePaise: 99900, currency: 'INR', durationMonths: 1, status: 'expired', startsAt: now - 120 * day, endsAt: now - 90 * day, daysRemaining: 0, source: 'admin_manual', createdAt: now - 120 * day, payment: { totalPaise: 99900, paidPaise: 99900, pendingPaise: 0 } },
      { id: 'mem-asha-cancelled', membershipNumber: 'GF-CANCELLED', customerId: 'cust-asha', planId: 'plan-basic', planName: 'Basic', pricePaise: 99900, currency: 'INR', durationMonths: 1, status: 'cancelled', startsAt: now - 180 * day, endsAt: now - 150 * day, daysRemaining: 0, source: 'admin_manual', createdAt: now - 180 * day, payment: { totalPaise: 99900, paidPaise: 0, pendingPaise: 99900 } },
    ],
    'cust-ravi': [
      { id: 'mem-ravi-live', membershipNumber: 'GF-2026-RAVI', customerId: 'cust-ravi', planId: 'plan-basic', planName: 'Basic', pricePaise: 99900, currency: 'INR', durationMonths: 1, status: 'active', startsAt: now - 20 * day, endsAt: now + 3 * day, daysRemaining: 3, source: 'admin_manual', createdAt: now - 20 * day, payment: { totalPaise: 99900, paidPaise: 99900, pendingPaise: 0 } },
      { id: 'mem-ravi-next', membershipNumber: 'GF-RAVI-NEXT', customerId: 'cust-ravi', planId: 'plan-pro', planName: 'Pro', pricePaise: 149900, currency: 'INR', durationMonths: 3, status: 'scheduled', startsAt: now + 3 * day, endsAt: now + 93 * day, daysRemaining: 0, source: 'admin_manual', createdAt: now - day, payment: { totalPaise: 149900, paidPaise: 0, pendingPaise: 149900 } },
    ],
    'cust-disabled': [],
  };
  const payments = [
    { id: 'pay-asha-1', membershipId: 'mem-asha-live', membershipNumber: 'GF-2026-ASHA', customerId: 'cust-asha', customerName: 'Asha Sharma', amountPaise: 50000, currency: 'INR', method: 'upi', note: 'Opening payment', paidAt: now - day, status: 'recorded' },
    { id: 'pay-ravi-1', membershipId: 'mem-ravi-live', membershipNumber: 'GF-2026-RAVI', customerId: 'cust-ravi', customerName: 'Ravi Patel', amountPaise: 99900, currency: 'INR', method: 'cash', note: null, paidAt: now - 2 * day, status: 'recorded' },
  ];
  const notifications = [
    { id: 'n-asha', membershipId: 'mem-asha-live', customerId: 'cust-asha', state: 'pending', triggerDays: 7, createdAt: now - 120 },
  ];
  const createBodies = [];
  const editBodies = [];
  const renewBodies = [];
  const paymentBodies = [];
  let customerMode = options.customerMode || 'ok';
  let paymentMode = options.paymentMode || 'ok';

  const findCustomer = (id) => customers.find((item) => item.id === id);
  const allMemberships = () => Object.values(memberships).flat();
  const findMembership = (id) => allMemberships().find((item) => item.id === id);
  const currentForList = (customerId) => {
    const rows = memberships[customerId] || [];
    return rows.find((item) => item.status === 'active') || rows.find((item) => item.status === 'scheduled') || rows.find((item) => item.status === 'expired') || rows.find((item) => item.status === 'cancelled') || null;
  };
  const customerListItem = (customer) => ({ ...customer, membership: currentForList(customer.id) });
  const customerDetail = (customerId) => {
    const customer = findCustomer(customerId);
    const rows = memberships[customerId] || [];
    return {
      customer: { ...customer },
      membership: {
        current: rows.find((item) => item.status === 'active') || null,
        upcoming: rows.find((item) => item.status === 'scheduled') || null,
        history: rows.filter((item) => ['expired', 'cancelled'].includes(item.status)),
        all: rows,
      },
      payments: payments.filter((item) => item.customerId === customerId).sort((a, b) => b.paidAt - a.paidAt),
      notifications: notifications.filter((item) => item.customerId === customerId),
    };
  };
  const feeRows = (query = '', pendingOnly = false) => {
    const needle = query.toLowerCase();
    return allMemberships().filter((membership) => membership.status !== 'cancelled').map((membership) => {
      const customer = findCustomer(membership.customerId);
      return { customerId: customer?.id, customerName: customer?.displayName, phone: customer?.phone, membership };
    }).filter((item) => (!needle || `${item.customerName || ''} ${item.phone || ''}`.toLowerCase().includes(needle)) && (!pendingOnly || Number(item.membership.payment?.pendingPaise || 0) > 0)).sort((a, b) => Number(b.membership.payment?.pendingPaise || 0) - Number(a.membership.payment?.pendingPaise || 0));
  };
  const dashboardPayload = () => {
    const pending = feeRows('', true);
    const active = allMemberships().filter((item) => item.status === 'active');
    const expiring = { today: [], tomorrow: [], threeDays: [], sevenDays: [] };
    for (const membership of active) {
      if (membership.daysRemaining > 7) continue;
      const customer = findCustomer(membership.customerId);
      const row = { customerId: membership.customerId, customerName: customer?.displayName, membershipId: membership.id, membershipNumber: membership.membershipNumber, planName: membership.planName, endsAt: membership.endsAt, status: membership.status };
      if (membership.daysRemaining <= 1) expiring.tomorrow.push(row);
      else if (membership.daysRemaining <= 3) expiring.threeDays.push(row);
      else expiring.sevenDays.push(row);
    }
    const pendingFees = pending.map((item) => ({ customerId: item.customerId, customerName: item.customerName, membershipId: item.membership.id, membershipNumber: item.membership.membershipNumber, planName: item.membership.planName, endsAt: item.membership.endsAt, ...item.membership.payment }));
    return {
      stats: {
        totalCustomers: customers.length,
        activeMembers: active.length,
        expiringSoon: Object.values(expiring).flat().length,
        expiredMembers: customers.filter((customer) => (memberships[customer.id] || []).some((m) => m.status === 'expired') && !(memberships[customer.id] || []).some((m) => ['active', 'scheduled'].includes(m.status))).length,
        pendingFeesTotalPaise: pending.reduce((sum, item) => sum + Number(item.membership.payment?.pendingPaise || 0), 0),
        newCustomersThisMonth: customers.filter((customer) => customer.createdAt >= now - 31 * day).length,
        paymentsReceivedTodayPaise: payments.filter((item) => item.paidAt >= now - day).reduce((sum, item) => sum + item.amountPaise, 0),
        paymentsReceivedThisMonthPaise: payments.filter((item) => item.paidAt >= now - 31 * day).reduce((sum, item) => sum + item.amountPaise, 0),
      },
      expiring,
      pendingFees: pendingFees.slice(0, 12),
      recentPayments: [...payments].sort((a, b) => b.paidAt - a.paidAt).slice(0, 8),
      recentCustomers: [...customers].sort((a, b) => b.createdAt - a.createdAt).slice(0, 8).map(customerListItem),
    };
  };
  const json = (route, status, body) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  await page.route('**/api/admin/session', (route) => json(route, 200, { configured: true, bootstrapRequired: false, authenticated: authState.authenticated, admin: authState.authenticated ? admin : undefined }));
  await page.route('**/api/admin/login', (route) => json(route, 200, { factorRequired: true }));
  await page.route('**/api/admin/verify', (route) => { authState.authenticated = true; return json(route, 200, { admin }); });
  await page.route('**/api/admin/logout', (route) => { authState.authenticated = false; return json(route, 200, {}); });
  await page.route(/\/api\/admin\/dashboard(?:\?.*)?$/, (route) => json(route, 200, dashboardPayload()));

  await page.route(/\/api\/admin\/customers(?:\?.*)?$/, async (route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON(); createBodies.push(body);
      if (customers.some((item) => item.phone === body.phone)) return json(route, 409, { error: 'admin_software_conflict' });
      if (!body.displayName || String(body.displayName).trim().length < 2 || !String(body.phone || '').startsWith('+')) return json(route, 422, { error: 'admin_software_validation', fields: { phone: 'Use an international mobile number such as +919876543210' } });
      const plan = plans.find((item) => item.id === body.planId); if (!plan) return json(route, 404, { error: 'admin_software_not_found' });
      const paid = Number(body.amountPaidPaise || 0); if (paid > plan.pricePaise) return json(route, 409, { error: 'admin_software_conflict' });
      const id = `cust-new-${createBodies.length}`; const customer = { id, displayName: body.displayName, phone: body.phone, phoneVerified: false, email: null, status: 'active', createdAt: now, lastLoginAt: null };
      customers.unshift(customer);
      const startsAt = Number(body.startsAt || now); const membership = { id: `mem-new-${createBodies.length}`, membershipNumber: `GF-NEW-${createBodies.length}`, customerId: id, planId: plan.id, planName: plan.name, pricePaise: plan.pricePaise, currency: plan.currency, durationMonths: plan.durationMonths, status: 'active', startsAt, endsAt: startsAt + plan.durationMonths * 30 * day, daysRemaining: plan.durationMonths * 30, source: 'admin_manual', createdAt: now, payment: { totalPaise: plan.pricePaise, paidPaise: paid, pendingPaise: plan.pricePaise - paid } };
      memberships[id] = [membership]; let payment = null;
      if (paid > 0) { payment = { id: `pay-new-${createBodies.length}`, membershipId: membership.id, membershipNumber: membership.membershipNumber, customerId: id, customerName: customer.displayName, amountPaise: paid, currency: plan.currency, method: body.paymentMethod, note: body.note || null, paidAt: now, status: 'recorded' }; payments.unshift(payment); }
      return json(route, 201, { customer, membership, payment, paymentSummary: membership.payment });
    }
    if (customerMode === 'error') return json(route, 503, { error: 'temporary_failure' });
    const params = new URL(route.request().url()).searchParams; const q = (params.get('q') || '').toLowerCase(); const status = params.get('status') || ''; const membershipStatus = params.get('membershipStatus') || ''; const planId = params.get('planId') || '';
    let rows = customers.filter((customer) => (!q || `${customer.displayName} ${customer.phone || ''}`.toLowerCase().includes(q)) && (!status || customer.status === status)).map(customerListItem);
    if (membershipStatus) rows = rows.filter((item) => (item.membership?.status || 'none') === membershipStatus);
    if (planId) rows = rows.filter((item) => item.membership?.planId === planId);
    return json(route, 200, { customers: customerMode === 'empty' ? [] : rows });
  });

  await page.route(/\/api\/admin\/customers\/[^/]+\/renew$/, async (route) => {
    const customerId = decodeURIComponent(new URL(route.request().url()).pathname.split('/').slice(-2)[0]);
    const body = route.request().postDataJSON(); renewBodies.push({ customerId, ...body });
    const plan = plans.find((item) => item.id === body.planId); if (!plan) return json(route, 404, { error: 'admin_software_not_found' });
    const paid = Number(body.amountPaidPaise || 0); if (paid > plan.pricePaise) return json(route, 409, { error: 'admin_software_conflict' });
    const current = (memberships[customerId] || []).find((item) => item.status === 'active'); const startsAt = Number(body.startsAt || current?.endsAt || now);
    const membership = { id: `renew-${renewBodies.length}`, membershipNumber: `GF-RENEW-${renewBodies.length}`, customerId, planId: plan.id, planName: plan.name, pricePaise: plan.pricePaise, currency: plan.currency, durationMonths: plan.durationMonths, status: current ? 'scheduled' : 'active', startsAt, endsAt: startsAt + plan.durationMonths * 30 * day, daysRemaining: current ? 0 : plan.durationMonths * 30, source: 'admin_manual', createdAt: now, payment: { totalPaise: plan.pricePaise, paidPaise: paid, pendingPaise: plan.pricePaise - paid } };
    memberships[customerId] = [membership, ...(memberships[customerId] || [])]; let payment = null;
    if (paid > 0) { const customer = findCustomer(customerId); payment = { id: `pay-renew-${renewBodies.length}`, membershipId: membership.id, membershipNumber: membership.membershipNumber, customerId, customerName: customer?.displayName, amountPaise: paid, currency: plan.currency, method: body.paymentMethod, note: body.note || null, paidAt: now, status: 'recorded' }; payments.unshift(payment); }
    return json(route, 201, { membership, payment, paymentSummary: membership.payment });
  });

  await page.route(/\/api\/admin\/customers\/[^/?]+(?:\?.*)?$/, async (route) => {
    const customerId = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop()); const customer = findCustomer(customerId); if (!customer) return json(route, 404, { error: 'admin_software_not_found' });
    if (route.request().method() === 'PATCH') {
      const body = route.request().postDataJSON(); editBodies.push({ customerId, ...body });
      if (body.phone && customers.some((item) => item.id !== customerId && item.phone === body.phone)) return json(route, 409, { error: 'admin_software_conflict' });
      Object.assign(customer, { ...(body.displayName !== undefined ? { displayName: body.displayName } : {}), ...(body.phone !== undefined ? { phone: body.phone, phoneVerified: false } : {}), ...(body.status !== undefined ? { status: body.status } : {}) });
      return json(route, 200, { customer: { ...customer } });
    }
    return json(route, 200, customerDetail(customerId));
  });

  await page.route(/\/api\/admin\/memberships\/[^/]+\/payments$/, async (route) => {
    const membershipId = decodeURIComponent(new URL(route.request().url()).pathname.split('/').slice(-2)[0]); const membership = findMembership(membershipId); if (!membership) return json(route, 404, { error: 'admin_software_not_found' });
    const body = route.request().postDataJSON();
    if (paymentMode === 'error') return json(route, 503, { error: 'temporary_failure' });
    paymentBodies.push({ membershipId, ...body }); await new Promise((resolve) => setTimeout(resolve, 120));
    const amount = Number(body.amountPaise || 0); if (amount <= 0) return json(route, 422, { error: 'admin_software_validation', fields: { amountPaidPaise: 'Amount must be greater than zero' } });
    if (amount > Number(membership.payment.pendingPaise || 0)) return json(route, 409, { error: 'admin_software_conflict' });
    membership.payment.paidPaise += amount; membership.payment.pendingPaise -= amount; const customer = findCustomer(membership.customerId);
    const payment = { id: `pay-ledger-${paymentBodies.length}`, membershipId, membershipNumber: membership.membershipNumber, customerId: membership.customerId, customerName: customer?.displayName, amountPaise: amount, currency: membership.currency, method: body.method, note: body.note || null, paidAt: Number(body.paidAt || now), status: 'recorded' }; payments.unshift(payment);
    return json(route, 201, { payment, summary: { ...membership.payment } });
  });

  await page.route(/\/api\/admin\/memberships(?:\?.*)?$/, (route) => {
    const params = new URL(route.request().url()).searchParams; const status = params.get('status') || ''; const planId = params.get('planId') || '';
    const rows = allMemberships().filter((membership) => (!status || membership.status === status) && (!planId || membership.planId === planId)).map((membership) => { const customer = findCustomer(membership.customerId); return { customer: { id: customer?.id, displayName: customer?.displayName, phone: customer?.phone }, membership }; });
    return json(route, 200, { memberships: rows });
  });

  await page.route(/\/api\/admin\/payments(?:\?.*)?$/, (route) => {
    const params = new URL(route.request().url()).searchParams; const customerId = params.get('customerId'); const membershipId = params.get('membershipId');
    const rows = payments.filter((item) => (!customerId || item.customerId === customerId) && (!membershipId || item.membershipId === membershipId)); return json(route, 200, { payments: rows });
  });
  await page.route(/\/api\/admin\/fees(?:\?.*)?$/, (route) => {
    const params = new URL(route.request().url()).searchParams; const rows = feeRows(params.get('q') || '', params.get('pendingOnly') === '1');
    return json(route, 200, { pendingFeesTotalPaise: rows.reduce((sum, item) => sum + Number(item.membership.payment?.pendingPaise || 0), 0), rows });
  });

  await page.route('**/api/admin/membership/plans', (route) => json(route, 200, { plans }));
  await page.route('**/api/admin/membership/plans/*', (route) => json(route, 200, { plan: plans[0] }));
  await page.route('**/api/admin/notifications?limit=100', (route) => json(route, 200, { providerBlockers: { email: 'READY', sms: 'BLOCKED_EXTERNAL_CONFIG', whatsapp: 'BLOCKED_EXTERNAL_CONFIG' }, notifications: [] }));
  await page.route('**/api/admin/notifications/scan', (route) => json(route, 200, { scan: { created: 0, deduped: 0, suppressedRenewed: 0 }, providerBlockers: {} }));
  await page.route('**/api/admin/admins', (route) => json(route, 200, { admins: [admin] }));
  await page.route('**/api/admin/audit?limit=100', (route) => json(route, 200, { audit: [] }));

  return { admin, customers, memberships, plans, payments, createBodies, editBodies, renewBodies, paymentBodies, setCustomerMode(value) { customerMode = value; }, setPaymentMode(value) { paymentMode = value; } };
}


test('admin login enters the operational gym dashboard', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  await mockAdminSoftware(page, { startUnauthenticated: true });
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/admin');
  await expect(page.locator('#login')).toBeVisible();
  await page.locator('#username').fill('owner');
  await page.locator('#password').fill('correct-horse-battery-staple');
  await page.getByRole('button', { name: 'Continue securely' }).click();
  await expect(page.locator('#factor')).toBeFocused();
  await page.locator('#factor').fill('123456');
  await page.getByRole('button', { name: /Verify/ }).click();
  await expect(page.locator('#app')).toBeVisible();
  await expect(page.locator('#viewTitle')).toHaveText('Dashboard');
  for (const label of ['Total Customers', 'Active Members', 'Expiring Soon', 'Expired Members', 'Pending Fees', 'New This Month', 'Payments Today', 'Payments This Month']) {
    await expect(page.locator('#stats')).toContainText(label);
  }
  await expect(page.locator('#dashboardExpiringBody')).toContainText('Asha Sharma');
  await expect(page.locator('#dashboardFeesState')).toContainText('Asha Sharma');
  await expect(page.locator('#recentPayments')).toContainText('Ravi Patel');
  await expect(page.locator('#recentCustomers')).toContainText('Ravi Patel');
  await expectNoOverflow(page);
  expect(runtimeProblems).toEqual([]);
});

test('customers workspace supports search filters detail history and status changes', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  const fixture = await mockAdminSoftware(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/admin');
  await page.locator('#membersNav').click();
  await page.locator('#memberSearch').fill('Asha');
  await expect(page.locator('#membersBody tr')).toHaveCount(1);
  await expect(page.locator('#membersBody')).toContainText('Pro');
  await expect(page.locator('#membersBody')).toContainText(/999/);
  await page.locator('#memberSearch').fill('');
  await page.locator('#customerMembershipFilter').selectOption('none');
  await expect(page.locator('#membersBody')).toContainText('Disabled Member');
  await page.locator('#customerMembershipFilter').selectOption('');
  await page.locator('#customerPlanFilter').selectOption('plan-pro');
  await expect(page.locator('#membersBody')).toContainText('Asha Sharma');
  await page.locator('#customerPlanFilter').selectOption('');
  await page.locator('#customerStatusFilter').selectOption('active');
  await page.locator('#membersBody').getByRole('button', { name: 'Open' }).first().click();
  const drawer = page.locator('#customerDrawer');
  await expect(drawer).toBeVisible();
  await expect(page.locator('#customerDrawerName')).toHaveText('Asha Sharma');
  await expect(drawer).toContainText('GF-2026-ASHA');
  await expect(drawer).toContainText('Payment history');
  await expect(drawer).toContainText('Opening payment');
  await expect(drawer).toContainText('7-day expiry reminder');
  await drawer.getByRole('button', { name: 'Edit Customer' }).click();
  await page.locator('#editCustomerName').fill('Asha Sharma Updated');
  await page.locator('#submitEditCustomer').click();
  await expect(page.locator('#editCustomerDialog')).not.toBeVisible();
  await expect(page.locator('#customerDrawerName')).toHaveText('Asha Sharma Updated');
  await drawer.getByRole('button', { name: 'Disable account' }).click();
  await expect(drawer).toContainText('disabled');
  await drawer.getByRole('button', { name: 'Enable account' }).click();
  await expect(drawer).toContainText('active');
  expect(fixture.editBodies.length).toBeGreaterThanOrEqual(3);
  await expectNoSeriousA11yFailures(page);
  expect(runtimeProblems).toEqual([]);
});

test('add customer is transactional accessible and rejects duplicate mobile', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  const fixture = await mockAdminSoftware(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/admin');
  const trigger = page.locator('#headerAddCustomer');
  await trigger.click();
  const dialog = page.locator('#addCustomerDialog');
  await expect(dialog).toBeVisible();
  await expect(page.locator('#newCustomerName')).toBeFocused();
  await page.locator('#newCustomerName').fill('New Member');
  await page.locator('#newCustomerMobile').fill('9876500000');
  await page.locator('#newCustomerReceived').fill('300');
  await page.locator('#newCustomerPaymentMethod').selectOption('upi');
  await page.locator('#newCustomerNote').fill('Reception onboarding');
  await expect(page.locator('#newCustomerFee')).toHaveValue(/999/);
  await expect(page.locator('#newCustomerPending')).toContainText(/699/);
  await expect(dialog).toContainText('Final membership dates and balances are calculated by the server.');
  for (let index = 0; index < 12; index += 1) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  }
  await page.locator('#submitNewCustomer').click();
  await expect(dialog).not.toBeVisible();
  await expect(page.locator('#customerDrawer')).toBeVisible();
  await expect(page.locator('#customerDrawerName')).toHaveText('New Member');
  await expect(page.locator('#customerDrawerBody')).toContainText(/699/);
  expect(fixture.createBodies[0].phone).toBe('+919876500000');
  expect(fixture.createBodies[0].amountPaidPaise).toBe(30000);
  await page.locator('#customerDrawer [aria-label="Close customer profile"]').click();
  await trigger.click();
  await page.locator('#newCustomerName').fill('Duplicate Asha');
  await page.locator('#newCustomerMobile').fill('9876543210');
  await page.locator('#submitNewCustomer').click();
  await expect(page.locator('#addCustomerError')).toHaveText('A customer with this mobile number already exists.');
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  expect(runtimeProblems.filter((problem) => !problem.includes('409 (Conflict)'))).toEqual([]);
});

test('renewal is server-backed with opening payment and preserved history', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  const fixture = await mockAdminSoftware(page);
  await page.goto('/admin');
  await page.locator('#membersNav').click();
  await page.locator('#membersBody').getByRole('button', { name: 'Open' }).first().click();
  const drawer = page.locator('#customerDrawer');
  await drawer.getByRole('button', { name: 'Renew Membership' }).click();
  await page.locator('#renewPlan').selectOption('plan-basic');
  await page.locator('#renewReceived').fill('250');
  await page.locator('#renewPaymentMethod').selectOption('cash');
  await page.locator('#renewNote').fill('Renewal deposit');
  await expect(page.locator('#renewPendingPreview')).toContainText(/749/);
  await page.locator('#submitRenewMembership').click();
  await expect(page.locator('#renewMembershipDialog')).not.toBeVisible();
  await expect.poll(() => fixture.renewBodies.length).toBe(1);
  expect(fixture.renewBodies[0].amountPaidPaise).toBe(25000);
  await expect(drawer).toContainText('GF-RENEW-1');
  await expect(drawer).toContainText('GF-2026-ASHA');
  await expect(drawer).toContainText('Renewal deposit');
  expect(runtimeProblems).toEqual([]);
});

test('manual payments support partial multiple full payment and double-submit protection', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  const fixture = await mockAdminSoftware(page);
  await page.goto('/admin');
  await page.locator('#membersNav').click();
  await page.locator('#membersBody').getByRole('button', { name: 'Open' }).first().click();
  const drawer = page.locator('#customerDrawer');
  await drawer.getByRole('button', { name: 'Record Payment' }).click();
  await expect(page.locator('#paymentPending')).toContainText(/999/);
  await page.locator('#paymentAmount').fill('400');
  await page.locator('#paymentMethod').selectOption('upi');
  const submit = page.locator('#submitPayment');
  await submit.click();
  await expect(submit).toBeDisabled();
  await expect.poll(() => fixture.paymentBodies.length).toBe(1);
  await expect(page.locator('#recordPaymentDialog')).not.toBeVisible();
  await expect(drawer).toContainText(/599/);
  await drawer.getByRole('button', { name: 'Record Payment' }).click();
  await expect(page.locator('#paymentPending')).toContainText(/599/);
  await page.locator('#paymentAmount').fill('599');
  await page.locator('#submitPayment').click();
  await expect.poll(() => fixture.paymentBodies.length).toBe(2);
  await expect(page.locator('#recordPaymentDialog')).not.toBeVisible();
  await expect(drawer.getByRole('button', { name: 'Record Payment' })).toBeDisabled();
  await expect(drawer).toContainText('Payment history');
  await expect(drawer).toContainText('UPI');
  expect(runtimeProblems).toEqual([]);
});

test('payment validation handles overpayment and network failure without mutating balance', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  const fixture = await mockAdminSoftware(page);
  await page.goto('/admin');
  await page.locator('#membersNav').click();
  await page.locator('#membersBody').getByRole('button', { name: 'Open' }).first().click();
  const drawer = page.locator('#customerDrawer');
  await drawer.getByRole('button', { name: 'Record Payment' }).click();
  await page.locator('#paymentAmount').fill('2000');
  expect(await page.locator('#paymentAmount').evaluate((node) => node.checkValidity())).toBe(false);
  await page.locator('#paymentAmount').fill('100');
  fixture.setPaymentMode('error');
  await page.locator('#submitPayment').click();
  await expect(page.locator('#paymentError')).toHaveText('The operation could not be completed. Please retry.');
  await expect(page.locator('#recordPaymentDialog')).toBeVisible();
  fixture.setPaymentMode('ok');
  await page.locator('#paymentAmount').fill('100');
  await page.locator('#submitPayment').click();
  await expect(page.locator('#recordPaymentDialog')).not.toBeVisible();
  await expect(drawer).toContainText(/899/);
  expect(runtimeProblems.filter((problem) => !problem.includes('503 (Service Unavailable)'))).toEqual([]);
});

test('fees workspace searches filters and records from the server ledger', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  await mockAdminSoftware(page);
  await page.goto('/admin');
  await page.locator('#feesNav').click();
  await expect(page.locator('#viewTitle')).toHaveText('Fees');
  await expect(page.locator('#feesPendingTotal')).toContainText(/2,498/);
  await expect(page.locator('#feesBody')).toContainText('Asha Sharma');
  await expect(page.locator('#feesBody')).toContainText('GF-RAVI-NEXT');
  await expect(page.locator('#feesBody')).not.toContainText('GF-2026-RAVI');
  await page.locator('#feeBalanceFilter').selectOption('all');
  await expect(page.locator('#feesBody')).toContainText('GF-2026-RAVI');
  await page.locator('#feeBalanceFilter').selectOption('paid');
  await expect(page.locator('#feesBody')).toContainText('GF-2026-RAVI');
  await expect(page.locator('#feesBody')).not.toContainText('GF-RAVI-NEXT');
  await page.locator('#feeBalanceFilter').selectOption('all');
  await page.locator('#feeSearch').fill('Asha');
  await expect(page.locator('#feesBody')).toContainText('Asha Sharma');
  await expect(page.locator('#feesBody')).not.toContainText('Ravi Patel');
  await page.locator('#feeSearch').fill('');
  await page.locator('#feeBalanceFilter').selectOption('pending');
  await page.locator('#feesBody tr').filter({ hasText: 'Asha Sharma' }).getByRole('button', { name: 'Record Payment' }).click();
  await expect(page.locator('#recordPaymentDialog')).toBeVisible();
  await expect(page.locator('#paymentCustomer')).toHaveText('Asha Sharma');
  expect(runtimeProblems).toEqual([]);
});

test('memberships workspace filters active scheduled expiring expired cancelled and plan', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  await mockAdminSoftware(page);
  await page.goto('/admin');
  await page.locator('#membershipsNav').click();
  await expect(page.locator('#membershipsBody')).toContainText('GF-2026-ASHA');
  await page.locator('#membershipStatusFilter').selectOption('active');
  await expect(page.locator('#membershipsBody')).toContainText('GF-2026-RAVI');
  await page.locator('#membershipStatusFilter').selectOption('expired');
  await expect(page.locator('#membershipsBody')).toContainText('GF-2026-OLD');
  await page.locator('#membershipStatusFilter').selectOption('cancelled');
  await expect(page.locator('#membershipsBody')).toContainText('GF-CANCELLED');
  await page.locator('#membershipStatusFilter').selectOption('scheduled');
  await expect(page.locator('#membershipsBody')).toContainText('GF-RAVI-NEXT');
  await page.locator('#membershipStatusFilter').selectOption('expiring');
  await page.locator('#expiryDays').selectOption('3');
  await expect(page.locator('#membershipsBody')).toContainText('Ravi Patel');
  await expect(page.locator('#membershipsBody')).not.toContainText('Asha Sharma');
  await page.locator('#membershipStatusFilter').selectOption('');
  await page.locator('#membershipPlanFilter').selectOption('plan-pro');
  await expect(page.locator('#membershipsBody')).toContainText('Pro');
  await expect(page.locator('.secondary-panel')).toContainText('Plan catalog');
  expect(runtimeProblems).toEqual([]);
});

test('admin software stays usable across desktop tablet mobile zoom keyboard and reduced motion', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const runtimeProblems = watchRuntime(page);
  await mockAdminSoftware(page);
  const adminWidths = [320, 360, 375, 390, 430, 768, 1024, 1366, 1440, 1920];
  for (const width of adminWidths) {
    await page.setViewportSize({ width, height: width <= 430 ? 844 : 900 });
    await page.goto('/admin');
    await expect(page.locator('#app')).toBeVisible();
    await expectNoOverflow(page);
    if (width <= 900) {
      await expect(page.locator('#sidebarOpen')).toBeVisible();
      await page.locator('#sidebarOpen').click();
      await expect(page.locator('#appSidebar')).toBeInViewport();
      await page.keyboard.press('Escape');
      await expect(page.locator('#sidebarOpen')).toBeFocused();
    } else {
      await expect(page.locator('#appSidebar')).toBeVisible();
      await expect(page.locator('#sidebarOpen')).not.toBeVisible();
    }
    if ([390, 1366].includes(width)) await page.screenshot({ path: testInfo.outputPath(`admin-software-v1-${width}.png`), fullPage: true });
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/admin');
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
  await expectNoOverflow(page);
  await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(await page.locator('#appSidebar').evaluate((node) => getComputedStyle(node).transitionDuration)).toBe('0s');
  await page.locator('#headerAddCustomer').focus();
  await page.keyboard.press('Enter');
  const dialog = page.locator('#addCustomerDialog');
  await expect(dialog).toBeVisible();
  for (let index = 0; index < 12; index += 1) {
    await page.keyboard.press('Tab');
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(page.locator('#headerAddCustomer')).toBeFocused();
  await expectNoSeriousA11yFailures(page);
  expect(runtimeProblems).toEqual([]);
});

test('admin customer empty and API failure states are explicit and console-safe', async ({ page }) => {
  const runtimeProblems = watchRuntime(page);
  const fixture = await mockAdminSoftware(page, { customerMode: 'empty' });
  await page.goto('/admin');
  await page.locator('#membersNav').click();
  await expect(page.locator('#membersBody')).toContainText('No customers match these filters.');
  fixture.setCustomerMode('error');
  await page.locator('#memberSearch').fill('failure');
  await expect(page.locator('#flash')).toBeVisible();
  await expect(page.locator('#flash')).toContainText('Customer list is temporarily unavailable.');
  expect(runtimeProblems.filter((problem) => !problem.includes('503 (Service Unavailable)'))).toEqual([]);
});
