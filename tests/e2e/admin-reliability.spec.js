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
  // "Home" is the intentional admin navigation label; the old "Dashboard" assertion was stale.
  await expect(page.locator('#viewTitle')).toHaveText('Home');

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
  await page.locator('#automaticMessagingPanel > summary').click();
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


test('biometric attendance and device workspaces are usable on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAdminShell(page, { authenticated: true }, ['dashboard.view', 'attendance.view', 'members.read', 'biometric.manage']);
  await page.route('**/api/admin/attendance/stats?*', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      stats: {
        date: '2026-09-01',
        presentToday: 1,
        members: 1,
        staff: 0,
        totalVisits: 1,
        devices: [{ id: 'device-1', name: 'Mock F09', status: 'online' }],
      },
    }),
  }));
  await page.route('**/api/admin/attendance?*', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      visits: [{
        id: 'visit-1',
        personId: 'person-1',
        displayName: 'Rahul Sharma',
        personType: 'member',
        membershipNumber: 'GF-001',
        membershipStatus: 'active',
        firstScanAt: 1788244200,
        lastScanAt: 1788244500,
        scanCount: 2,
        deviceName: 'Mock F09',
      }],
      unmatched: [],
    }),
  }));
  await page.route('**/api/admin/biometric/devices', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      devices: [{
        id: 'device-1',
        name: 'Mock F09',
        vendor: 'zkteco',
        model: 'F09',
        deviceIdentifier: '1',
        host: '192.168.1.201',
        port: 4370,
        status: 'online',
        connectionMode: 'mock',
        commKeyConfigured: false,
      }],
    }),
  }));
  await page.route('**/api/admin/biometric/mappings', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      mappings: [{ id: 'map-1', deviceId: 'device-1', deviceName: 'Mock F09', deviceUserId: '101', person: { displayName: 'Rahul Sharma', personType: 'member' } }],
    }),
  }));
  await page.route('**/api/admin/customers?*', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ customers: [{ id: 'person-1', displayName: 'Rahul Sharma', personType: 'member', membership: { membershipNumber: 'GF-001' } }] }),
  }));

  await page.goto('/admin');
  await page.locator('#sidebarOpen').click();
  await page.locator('#attendanceNav').click();
  await expect(page.locator('#viewTitle')).toHaveText('Attendance');
  await expect(page.locator('#attendanceMobileList')).toContainText('Rahul Sharma');
  await expect(page.locator('#attendanceMobileList')).toContainText('Mock F09');

  await page.locator('#sidebarOpen').click();
  await page.locator('#advancedNav > summary').click();
  await page.locator('#biometricNav').click();
  await expect(page.locator('#viewTitle')).toHaveText('Biometric Devices');
  await expect(page.locator('#biometricDevices')).toContainText('Mock F09');
  await expect(page.locator('#biometricMappings')).toContainText('user 101');
});
