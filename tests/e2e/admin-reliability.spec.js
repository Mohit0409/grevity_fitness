const { test, expect } = require('@playwright/test');


function adminIdentity(permissions = ['*']) {
  return { id: 'admin-reliability', username: 'owner', role: 'owner', permissions };
}


async function mockAdminShell(page, sessionState, permissions = ['*']) {
  await page.route('**/api/admin/session', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(sessionState.authenticated
      ? { configured: true, bootstrapRequired: false, authenticated: true, admin: adminIdentity(permissions) }
      : { configured: true, bootstrapRequired: false, authenticated: false }),
  }));
  await page.route('**/api/admin/dashboard', (route) => route.fulfill({
    status: sessionState.authenticated ? 200 : 401,
    contentType: 'application/json',
    body: JSON.stringify(sessionState.authenticated
      ? { customers: { total: 0, active: 0, disabled: 0 }, admins: { owner: 1 }, recentAudit: [] }
      : { error: 'admin_unauthenticated' }),
  }));
}


test('admin refresh, history navigation, and expired session fail safely', async ({ page }) => {
  const sessionState = { authenticated: true };
  await mockAdminShell(page, sessionState);

  await page.goto('/admin');
  await expect(page.locator('#app')).toBeVisible();
  await expect(page.locator('#viewTitle')).toHaveText('Dashboard');

  await page.reload();
  await expect(page.locator('#app')).toBeVisible();
  await page.goto('/');
  await page.goBack();
  await expect(page.locator('#app')).toBeVisible();

  sessionState.authenticated = false;
  await page.reload();
  await expect(page.locator('#login')).toBeVisible();
  await expect(page.locator('#app')).toBeHidden();
});


test('slow and interrupted notification APIs remain usable and scan double-click is rejected', async ({ page }) => {
  const sessionState = { authenticated: true };
  await mockAdminShell(page, sessionState, ['notifications.manage']);
  let scanCalls = 0;
  let failList = false;
  await page.route('**/api/admin/notifications?limit=100', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    if (failList) {
      await route.abort('internetdisconnected');
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        notifications: [],
        providerBlockers: { email: 'READY', sms: 'BLOCKED_EXTERNAL_CONFIG', whatsapp: 'BLOCKED_EXTERNAL_CONFIG' },
      }),
    });
  });
  await page.route('**/api/admin/notifications/scan', async (route) => {
    scanCalls += 1;
    await new Promise((resolve) => setTimeout(resolve, 400));
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ scan: { created: 0, deduped: 0, suppressedRenewed: 0 } }),
    });
  });

  await page.goto('/admin');
  await page.locator('#notificationsNav').click();
  await expect(page.locator('#notificationsList')).toHaveAttribute('aria-busy', 'false');
  await page.evaluate(() => {
    const button = document.querySelector('#scanNotifications');
    button.click();
    button.click();
  });
  await expect(page.locator('#scanNotifications')).toBeDisabled();
  await expect.poll(() => scanCalls).toBe(1);
  await expect(page.locator('#scanNotifications')).toBeEnabled();

  failList = true;
  await page.evaluate(() => { void window.GravityNotificationAdmin.renderWorkspace(); });
  await expect(page.locator('#notificationsList')).toContainText('temporarily unavailable');
  await expect(page.locator('#app')).toBeVisible();
});
