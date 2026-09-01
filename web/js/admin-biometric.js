(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, devices: [], mappings: [], people: [], searchTimer: null, attendanceTimer: null, editingDevice: null };
  const core = () => window.GravityAdminCore;

  function hasPermission(permission) { return core()?.hasPermission(permission) || false; }
  function api(path, options = {}) { return core().api(path, options); }
  function flash(message, kind = 'ok') { return core().flash(message, kind); }
  function formatTime(value) { return core()?.formatTime(value) || '--'; }

  function todayInput() {
    const date = new Date();
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }

  function badge(status) {
    const span = document.createElement('span');
    span.className = `badge badge--${String(status || 'unknown').replaceAll('_', '-')}`;
    span.textContent = String(status || 'unknown').replaceAll('_', ' ');
    return span;
  }

  function empty(message, className = 'software-empty') {
    const node = document.createElement('p');
    node.className = className;
    node.textContent = message;
    return node;
  }

  function tableEmpty(message, colspan) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = colspan;
    cell.className = 'empty';
    cell.textContent = message;
    row.appendChild(cell);
    return row;
  }

  function setBusy(node, busy, label = 'Working...') {
    if (!node) return;
    if (busy) {
      node.dataset.idleLabel = node.textContent;
      node.textContent = label;
      node.disabled = true;
    } else {
      node.textContent = node.dataset.idleLabel || node.textContent;
      node.disabled = false;
    }
  }

  function deviceLabel(device) {
    return `${device.name || 'Biometric machine'} (${device.connectionMode || 'tcp'}:${device.deviceIdentifier || '1'})`;
  }

  function verificationText(value) {
    const labels = { fingerprint: 'Fingerprint', face: 'Face', card: 'Card', password: 'Password', unknown: 'Unknown' };
    const parts = String(value || 'unknown').split(',').map((item) => item.trim()).filter(Boolean);
    return parts.map((item) => labels[item] || item.replaceAll('_', ' ')).join(' + ') || 'Unknown';
  }

  function personLabel(person) {
    const type = person.personType === 'staff' ? 'Staff' : 'Member';
    const detail = person.personType === 'staff' ? person.designation : person.membership?.membershipNumber;
    return `${person.displayName || 'Person'} - ${type}${detail ? ` - ${detail}` : ''}`;
  }

  function membershipStatus(item) {
    if (item.personType === 'staff') return item.staffDesignation || 'Staff';
    return item.membershipStatus || 'none';
  }

  function renderStat(label, value, hint = '') {
    const card = document.createElement('article');
    card.className = 'software-stat';
    const small = document.createElement('small'); small.textContent = label;
    const strong = document.createElement('strong'); strong.textContent = String(value ?? 0);
    card.append(small, strong);
    if (hint) { const note = document.createElement('span'); note.textContent = hint; card.appendChild(note); }
    return card;
  }

  async function renderAttendanceWorkspace() {
    if (!$('attendanceDate').value) $('attendanceDate').value = todayInput();
    const panel = $('attendancePanel');
    panel?.setAttribute('aria-busy', 'true');
    try {
      const params = new URLSearchParams();
      params.set('date', $('attendanceDate').value);
      if ($('attendanceSearch').value.trim()) params.set('q', $('attendanceSearch').value.trim());
      if ($('attendancePersonType').value) params.set('personType', $('attendancePersonType').value);
      if ($('attendanceMembershipStatus').value) params.set('membershipStatus', $('attendanceMembershipStatus').value);
      const [statsPayload, attendancePayload] = await Promise.all([
        api(`/api/admin/attendance/stats?date=${encodeURIComponent($('attendanceDate').value)}`),
        api(`/api/admin/attendance?${params.toString()}`),
      ]);
      renderAttendanceStats(statsPayload.stats || {});
      renderAttendanceRows(attendancePayload.visits || []);
      renderUnmatched(attendancePayload.unmatched || []);
      $('attendanceExport').href = `/api/admin/attendance/export?${params.toString()}`;
    } catch (error) {
      $('attendanceBody').replaceChildren(tableEmpty('Attendance is temporarily unavailable. Retry after the service is online.', 7));
      $('attendanceMobileList').replaceChildren(empty('Attendance is temporarily unavailable.', 'software-empty error-state'));
      flash(error.message || 'Attendance is temporarily unavailable.', 'error');
    } finally {
      panel?.setAttribute('aria-busy', 'false');
    }
  }

  function renderAttendanceStats(stats) {
    const root = $('attendanceStats');
    root.replaceChildren(
      renderStat('Present today', stats.presentToday || 0, stats.date || ''),
      renderStat('Members', stats.members || 0),
      renderStat('Staff', stats.staff || 0),
      renderStat('Fingerprint scans', stats.verificationCounts?.fingerprint || 0),
      renderStat('Face scans', stats.verificationCounts?.face || 0),
      renderStat('Device status', (stats.devices || []).filter((device) => device.status === 'online').length, `${(stats.devices || []).length} configured`)
    );
  }

  function renderAttendanceRows(rows) {
    const body = $('attendanceBody');
    const mobile = $('attendanceMobileList');
    body.replaceChildren();
    mobile.replaceChildren();
    for (const item of rows) {
      const row = document.createElement('tr');
      const person = document.createElement('td');
      const name = document.createElement('button');
      name.type = 'button';
      name.className = 'lead-link';
      name.textContent = item.displayName || item.personId || 'Person';
      name.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById?.(item.personId, name));
      person.appendChild(name);
      const type = document.createElement('td'); type.textContent = item.personType || '--';
      const member = document.createElement('td');
      member.appendChild(badge(membershipStatus(item)));
      if (item.membershipNumber) {
        const number = document.createElement('small');
        number.textContent = item.membershipNumber;
        member.append(document.createElement('br'), number);
      }
      const first = document.createElement('td'); first.textContent = formatTime(item.firstScanAt);
      const last = document.createElement('td'); last.textContent = formatTime(item.lastScanAt);
      const scans = document.createElement('td'); scans.textContent = String(item.scanCount || 0);
      const verification = document.createElement('td'); verification.textContent = verificationText(item.verificationSummary);
      const device = document.createElement('td'); device.textContent = item.deviceName || '--';
      row.append(person, type, member, first, last, scans, verification, device);
      body.appendChild(row);

      const card = document.createElement('article');
      card.className = 'mobile-record attendance-mobile-card';
      card.setAttribute('role', 'listitem');
      const head = document.createElement('div'); head.className = 'mobile-record-head';
      const label = document.createElement('div');
      const strong = document.createElement('strong'); strong.textContent = item.displayName || 'Person';
      const small = document.createElement('small'); small.textContent = `${item.personType || '--'} - ${device.textContent}`;
      label.append(strong, small);
      head.append(label, badge(membershipStatus(item)));
      const facts = document.createElement('dl'); facts.className = 'mobile-record-facts';
      [['First', formatTime(item.firstScanAt)], ['Last', formatTime(item.lastScanAt)], ['Scans', String(item.scanCount || 0)], ['Verified by', verificationText(item.verificationSummary)]].forEach(([key, value]) => {
        const div = document.createElement('div');
        const dt = document.createElement('dt'); dt.textContent = key;
        const dd = document.createElement('dd'); dd.textContent = value;
        div.append(dt, dd); facts.appendChild(div);
      });
      const open = document.createElement('button');
      open.type = 'button'; open.className = 'table-action full-width'; open.textContent = 'Open profile';
      open.addEventListener('click', () => window.GravityCustomerAdmin?.openCustomerById?.(item.personId, open));
      card.append(head, facts, open);
      mobile.appendChild(card);
    }
    if (!body.children.length) body.appendChild(tableEmpty('No attendance visits match these filters.', 8));
    if (!mobile.children.length) mobile.appendChild(empty('No attendance visits match these filters.'));
  }

  function renderUnmatched(rows) {
    const root = $('unmatchedAttendanceList');
    if (!root) return;
    root.replaceChildren();
    for (const item of rows) {
      const card = document.createElement('article');
      card.className = 'biometric-card';
      card.setAttribute('role', 'listitem');
      const title = document.createElement('h4');
      title.textContent = item.deviceDisplayName || `User ID ${item.deviceUserId}`;
      const meta = document.createElement('p');
      meta.className = 'micro';
      meta.textContent = `${item.deviceName || 'Device'} - ${verificationText(item.verificationType)} - ${formatTime(item.eventTime || item.lastSeenAt)}`;
      const action = document.createElement('button');
      action.type = 'button';
      action.className = 'ghost';
      action.textContent = 'Map this ID';
      action.disabled = !hasPermission('biometric.manage');
      action.addEventListener('click', async () => {
        await renderDeviceWorkspace();
        $('mappingDevice').value = item.deviceId;
        $('mappingDeviceUserId').value = item.deviceUserId;
        $('mappingPersonSearch').focus();
      });
      card.append(title, meta, action);
      root.appendChild(card);
    }
    if (!root.children.length) root.appendChild(empty('No unmatched scans for the selected day.'));
  }

  async function renderDeviceWorkspace() {
    const devicesPanel = $('biometricDevicesPanel');
    const mappingsPanel = $('biometricMappingsPanel');
    devicesPanel?.setAttribute('aria-busy', 'true');
    mappingsPanel?.setAttribute('aria-busy', 'true');
    try {
      const [devicePayload, mappingPayload] = await Promise.all([
        api('/api/admin/biometric/devices'),
        api('/api/admin/biometric/mappings'),
      ]);
      state.devices = devicePayload.devices || [];
      state.mappings = mappingPayload.mappings || [];
      renderDevices();
      renderMappingOptions();
      renderMappings();
      await searchPeople();
    } catch (error) {
      $('biometricDevices').replaceChildren(empty('Biometric devices are temporarily unavailable.', 'software-empty error-state'));
      flash(error.message || 'Biometric devices are temporarily unavailable.', 'error');
    } finally {
      devicesPanel?.setAttribute('aria-busy', 'false');
      mappingsPanel?.setAttribute('aria-busy', 'false');
    }
  }

  function renderDevices() {
    const root = $('biometricDevices');
    root.replaceChildren();
    for (const device of state.devices) {
      const card = document.createElement('article');
      card.className = 'biometric-card';
      card.setAttribute('role', 'listitem');
      const head = document.createElement('div'); head.className = 'biometric-card-head';
      const title = document.createElement('div');
      const h = document.createElement('h4'); h.textContent = device.name || 'Biometric machine';
      const meta = document.createElement('p'); meta.className = 'micro';
      meta.textContent = `${device.vendor || 'zkteco'} ${device.model || 'F09'} - ${device.host || 'no IP'}:${device.port || 4370}`;
      title.append(h, meta); head.append(title, badge(device.status || 'not_configured'));
      const facts = document.createElement('dl');
      facts.className = 'biometric-facts';
      [
        ['Device ID', device.deviceIdentifier || '1'],
        ['Mode', device.connectionMode || 'tcp'],
        ['Comm key', device.commKeyConfigured ? 'configured' : 'not saved'],
        ['Last sync', device.lastSyncAt ? formatTime(device.lastSyncAt) : 'never'],
      ].forEach(([key, value]) => {
        const div = document.createElement('div');
        const dt = document.createElement('dt'); dt.textContent = key;
        const dd = document.createElement('dd'); dd.textContent = value;
        div.append(dt, dd); facts.appendChild(div);
      });
      const actions = document.createElement('div');
      actions.className = 'row-actions';
      const edit = document.createElement('button'); edit.type = 'button'; edit.className = 'ghost'; edit.textContent = 'Edit';
      const test = document.createElement('button'); test.type = 'button'; test.textContent = 'Test';
      const sync = document.createElement('button'); sync.type = 'button'; sync.className = 'ghost'; sync.textContent = 'Sync';
      edit.disabled = test.disabled = sync.disabled = !hasPermission('biometric.manage');
      edit.addEventListener('click', () => openDeviceDialog(device));
      test.addEventListener('click', () => testDevice(device.id, test));
      sync.addEventListener('click', () => syncDevice(device.id, sync));
      actions.append(edit, test, sync);
      if (device.connectionMode === 'mock' && hasPermission('biometric.manage')) {
        for (const [method, label] of [['fingerprint', 'Simulate fingerprint'], ['face', 'Simulate face']]) {
          const simulate = document.createElement('button');
          simulate.type = 'button'; simulate.className = 'ghost'; simulate.textContent = label;
          simulate.addEventListener('click', () => simulateScan(device.id, simulate, method));
          actions.appendChild(simulate);
        }
      }
      card.append(head, facts, actions);
      root.appendChild(card);
    }
    if (!root.children.length) root.appendChild(empty('No biometric machine configured yet. Add the F09 in TCP mode later, or mock mode for fingerprint/face testing.'));
  }

  function renderMappingOptions() {
    const select = $('mappingDevice');
    const current = select.value;
    select.replaceChildren();
    for (const device of state.devices) select.appendChild(new Option(deviceLabel(device), device.id));
    if (Array.from(select.options).some((option) => option.value === current)) select.value = current;
  }

  async function searchPeople() {
    const query = $('mappingPersonSearch')?.value?.trim() || '';
    const payload = await api(`/api/admin/customers?personType=&limit=50&q=${encodeURIComponent(query)}`);
    state.people = payload.customers || [];
    const select = $('mappingPerson');
    const current = select.value;
    select.replaceChildren();
    for (const person of state.people) select.appendChild(new Option(personLabel(person), person.id));
    if (Array.from(select.options).some((option) => option.value === current)) select.value = current;
  }

  function renderMappings() {
    const root = $('biometricMappings');
    root.replaceChildren();
    for (const item of state.mappings) {
      const row = document.createElement('article');
      row.className = 'biometric-list-row';
      const text = document.createElement('div');
      const strong = document.createElement('strong');
      strong.textContent = item.person?.displayName || item.personId || 'Person';
      const small = document.createElement('small');
      small.textContent = `${item.person?.personType || '--'} - ${item.deviceName || 'Device'} - user ${item.deviceUserId}`;
      text.append(strong, small);
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'ghost'; remove.textContent = 'Unlink';
      remove.disabled = !hasPermission('biometric.manage');
      remove.addEventListener('click', () => removeMapping(item.id, remove));
      row.append(text, remove);
      root.appendChild(row);
    }
    if (!root.children.length) root.appendChild(empty('No user IDs are mapped yet.'));
  }

  function openDeviceDialog(device = null) {
    state.editingDevice = device;
    $('biometricDeviceForm').reset();
    $('biometricDeviceId').value = device?.id || '';
    $('biometricDeviceTitle').textContent = device ? 'Edit biometric machine' : 'Add biometric machine';
    $('biometricName').value = device?.name || 'Gravity Entrance F09';
    $('biometricMode').value = device?.connectionMode || 'tcp';
    $('biometricModel').value = device?.model || 'F09';
    $('biometricIdentifier').value = device?.deviceIdentifier || '1';
    $('biometricHost').value = device?.host || (device?.connectionMode === 'mock' ? '' : '192.168.1.201');
    $('biometricPort').value = device?.port || 4370;
    $('biometricTimezone').value = device?.timezone || 'Asia/Kolkata';
    $('biometricDuplicateWindow').value = device?.duplicateWindowSeconds || 120;
    $('biometricVisitGap').value = device?.visitGapSeconds || 14400;
    $('biometricCommKey').value = '';
    $('biometricDeviceError').textContent = '';
    const dialog = $('biometricDeviceDialog');
    if (!dialog.open) dialog.showModal();
    $('biometricName').focus();
  }

  async function saveDevice(event) {
    event.preventDefault();
    const button = $('submitBiometricDevice');
    $('biometricDeviceError').textContent = '';
    setBusy(button, true, 'Saving...');
    const mode = $('biometricMode').value;
    const body = {
      name: $('biometricName').value.trim(),
      vendor: 'zkteco',
      model: $('biometricModel').value.trim() || 'F09',
      deviceIdentifier: $('biometricIdentifier').value.trim() || '1',
      host: $('biometricHost').value.trim(),
      port: Number($('biometricPort').value || 4370),
      connectionMode: mode,
      timezone: $('biometricTimezone').value.trim() || 'Asia/Kolkata',
      duplicateWindowSeconds: Number($('biometricDuplicateWindow').value || 120),
      visitGapSeconds: Number($('biometricVisitGap').value || 14400),
    };
    if (mode === 'mock') body.host = '';
    if ($('biometricCommKey').value) body.commKey = $('biometricCommKey').value;
    try {
      if ($('biometricDeviceId').value) {
        await api(`/api/admin/biometric/devices/${encodeURIComponent($('biometricDeviceId').value)}`, { method: 'PATCH', body });
      } else {
        await api('/api/admin/biometric/devices', { method: 'POST', body });
      }
      $('biometricDeviceDialog').close();
      flash('Biometric device saved.');
      await renderDeviceWorkspace();
    } catch (error) {
      const fields = error?.data?.fields || {};
      $('biometricDeviceError').textContent = Object.values(fields)[0] || 'Could not save the biometric machine.';
    } finally {
      setBusy(button, false);
    }
  }

  async function testDevice(deviceId, button) {
    setBusy(button, true, 'Testing...');
    try {
      await api(`/api/admin/biometric/devices/${encodeURIComponent(deviceId)}/test`, { method: 'POST' });
      flash('Device test completed.');
      await renderDeviceWorkspace();
    } catch (error) {
      flash(error.status === 503 ? 'Device is offline or rejected the communication key.' : error.message, 'error');
      await renderDeviceWorkspace();
    } finally { setBusy(button, false); }
  }

  async function syncDevice(deviceId, button) {
    setBusy(button, true, 'Syncing...');
    try {
      const result = await api(`/api/admin/biometric/devices/${encodeURIComponent(deviceId)}/sync`, { method: 'POST' });
      flash(`Sync complete: ${result.stored || 0} scan(s), ${result.unmatched || 0} unmatched.`);
      await renderDeviceWorkspace();
      await renderAttendanceWorkspace();
    } catch (error) {
      flash(error.status === 503 ? 'Sync failed: device offline or Comm Key rejected.' : error.message, 'error');
      await renderDeviceWorkspace();
    } finally { setBusy(button, false); }
  }

  async function simulateScan(deviceId, button, verificationType = 'fingerprint') {
    setBusy(button, true, 'Scanning...');
    const mapped = state.mappings.find((item) => item.deviceId === deviceId);
    const deviceUserId = mapped?.deviceUserId || `mock-${Math.floor(Math.random() * 900 + 100)}`;
    try {
      await api('/api/admin/biometric/simulate', {
        method: 'POST',
        body: { deviceId, deviceUserId, eventTime: Math.floor(Date.now() / 1000), verificationType, attendanceState: 'check-in' },
      });
      flash(`Mock ${verificationText(verificationType).toLowerCase()} scan stored for user ${deviceUserId}.`);
      await renderAttendanceWorkspace();
      await renderDeviceWorkspace();
    } catch (error) {
      flash('Mock scan could not be stored.', 'error');
    } finally { setBusy(button, false); }
  }

  async function createMapping(event) {
    event.preventDefault();
    try {
      await api('/api/admin/biometric/mappings', {
        method: 'POST',
        body: {
          deviceId: $('mappingDevice').value,
          deviceUserId: $('mappingDeviceUserId').value.trim(),
          personId: $('mappingPerson').value,
          enrolledStatus: 'registered',
        },
      });
      $('mappingDeviceUserId').value = '';
      flash('Biometric user ID linked.');
      await renderDeviceWorkspace();
      await renderAttendanceWorkspace();
    } catch (error) {
      const fields = error?.data?.fields || {};
      flash(Object.values(fields)[0] || 'Could not link that biometric user ID.', 'error');
    }
  }

  async function removeMapping(mappingId, button) {
    setBusy(button, true, 'Unlinking...');
    try {
      await api(`/api/admin/biometric/mappings/${encodeURIComponent(mappingId)}`, { method: 'DELETE' });
      flash('Biometric user ID unlinked. Past attendance remains stored.');
      await renderDeviceWorkspace();
    } catch (error) {
      flash('Could not unlink that biometric user ID.', 'error');
    } finally { setBusy(button, false); }
  }

  async function renderPersonAttendance(root, person) {
    if (!root || !person?.id || !hasPermission('attendance.view')) return;
    const section = document.createElement('section');
    section.className = 'profile-section biometric-profile-section';
    const head = document.createElement('div');
    head.className = 'profile-section-head';
    const h = document.createElement('h4'); h.textContent = 'Attendance';
    head.appendChild(h);
    const holder = document.createElement('div');
    holder.className = 'mini-history';
    holder.appendChild(empty('Loading attendance...'));
    section.append(head, holder);
    root.appendChild(section);
    try {
      const payload = await api(`/api/admin/attendance/person/${encodeURIComponent(person.id)}`);
      const data = payload.attendance || {};
      holder.replaceChildren();
      const summary = document.createElement('div');
      summary.className = 'attendance-profile-summary';
      [
        ['Today', data.today ? 'Present' : 'No scan'],
        ['Last 7 days', data.last7Days || 0],
        ['This month', data.thisMonth || 0],
        ['Last visit', data.lastVisit ? formatTime(data.lastVisit.firstScanAt) : '--'],
      ].forEach(([key, value]) => {
        const item = document.createElement('span');
        item.append(document.createTextNode(key));
        const strong = document.createElement('strong');
        strong.textContent = String(value);
        item.appendChild(strong);
        summary.appendChild(item);
      });
      holder.appendChild(summary);
      for (const visit of data.recentVisits || []) {
        const row = document.createElement('div');
        row.className = 'mini-history-row';
        const text = document.createElement('span');
        const title = document.createElement('strong');
        title.textContent = `${visit.date || '--'} - ${visit.scanCount || 0} scan(s)`;
        const meta = document.createElement('small');
        meta.textContent = `${formatTime(visit.firstScanAt)} to ${formatTime(visit.lastScanAt)} - ${visit.deviceName || 'Device'}`;
        text.append(title, meta);
        row.append(text, badge(visit.verificationSummary || 'scan'));
        holder.appendChild(row);
      }
      if (!(data.recentVisits || []).length) holder.appendChild(empty('No biometric attendance yet.'));
    } catch (_) {
      holder.replaceChildren(empty('Attendance history is temporarily unavailable.', 'software-empty error-state'));
    }
  }

  function wire() {
    $('newBiometricDevice')?.addEventListener('click', () => openDeviceDialog());
    $('refreshBiometricDevices')?.addEventListener('click', () => renderDeviceWorkspace());
    $('refreshAttendance')?.addEventListener('click', () => renderAttendanceWorkspace());
    $('biometricDeviceForm')?.addEventListener('submit', saveDevice);
    $('biometricMappingForm')?.addEventListener('submit', createMapping);
    ['attendanceDate', 'attendancePersonType', 'attendanceMembershipStatus'].forEach((id) => $(id)?.addEventListener('change', () => renderAttendanceWorkspace()));
    $('attendanceSearch')?.addEventListener('input', () => {
      window.clearTimeout(state.attendanceTimer);
      state.attendanceTimer = window.setTimeout(() => renderAttendanceWorkspace(), 220);
    });
    $('mappingPersonSearch')?.addEventListener('input', () => {
      window.clearTimeout(state.searchTimer);
      state.searchTimer = window.setTimeout(() => searchPeople().catch(() => flash('Person search is unavailable.', 'error')), 220);
    });
    document.querySelectorAll('[data-close-dialog]').forEach((button) => {
      button.addEventListener('click', () => $(button.dataset.closeDialog)?.close());
    });
  }

  window.GravityBiometricAdmin = {
    setAdmin(admin) { state.admin = admin; },
    renderAttendanceWorkspace,
    renderDeviceWorkspace,
    renderPersonAttendance,
  };

  wire();
})();
