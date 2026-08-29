(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const state = { admin: null, memberId: '', members: [], templates: [], versions: [] };

  function hasPermission(permission) {
    const permissions = state.admin?.permissions || [];
    return permissions.includes('*') || permissions.includes(permission);
  }

  function canCoach() {
    return hasPermission('progress.manage') && hasPermission('diet.manage');
  }

  function csrfToken() {
    const part = document.cookie.split(';').map((item) => item.trim()).find((item) =>
      item.startsWith('gravity_admin_csrf=') || item.startsWith('__Host-gravity_admin_csrf=')
    );
    return part ? decodeURIComponent(part.slice(part.indexOf('=') + 1)) : '';
  }

  function flash(message, kind = 'ok') {
    const node = $('flash');
    node.textContent = message;
    node.className = `flash ${kind}`;
    node.hidden = false;
    window.clearTimeout(node._coachingTimer);
    node._coachingTimer = window.setTimeout(() => { node.hidden = true; }, 4500);
  }

  async function api(path, options = {}) {
    const request = { credentials: 'same-origin', ...options };
    request.headers = { Accept: 'application/json', ...(options.headers || {}) };
    if (options.body && typeof options.body !== 'string') {
      request.body = JSON.stringify(options.body);
      request.headers['Content-Type'] = 'application/json';
    }
    if (request.method && !['GET', 'HEAD'].includes(request.method)) {
      const csrf = csrfToken();
      if (csrf) request.headers['X-CSRF-Token'] = csrf;
    }
    const response = await fetch(path, request);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401) await window.GravityAdminCore?.refreshSession?.();
      const error = new Error(data.error || `HTTP ${response.status}`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
  }

  function selectedMember() {
    return $('coachingMember').value || state.memberId;
  }

  function selectedTemplate() {
    return state.templates.find((item) => item.id === $('dietTemplateSelect').value) || null;
  }

  async function syncAdmin() {
    const session = await api('/api/admin/session');
    if (!session.authenticated || !session.admin) return null;
    state.admin = session.admin;
    $('coachingNav').hidden = !canCoach();
    return state.admin;
  }

  async function loadMembers() {
    const payload = await api('/api/admin/members?q=');
    state.members = payload.members || [];
    const select = $('coachingMember');
    const previous = select.value || state.memberId;
    select.replaceChildren();
    for (const member of state.members) {
      const option = document.createElement('option');
      option.value = member.id;
      option.textContent = member.displayName || member.email || member.phone || member.id;
      select.appendChild(option);
    }
    if (previous && state.members.some((item) => item.id === previous)) select.value = previous;
    state.memberId = select.value || '';
  }

  function summaryText(summary) {
    const measurements = Object.values(summary.latestMeasurements || {});
    const activeGoals = (summary.goals || []).filter((goal) => goal.status === 'active');
    const diet = summary.currentDiet?.plan;
    return `${measurements.length} latest measurements · ${activeGoals.length} active goals · ${diet ? `${diet.title} v${diet.version}` : 'no active nutrition plan'}`;
  }

  async function renderMember() {
    state.memberId = selectedMember();
    const box = $('coachingProgressList');
    box.replaceChildren();
    if (!state.memberId) {
      $('coachingMemberSummary').textContent = 'No active members are available.';
      return;
    }
    const payload = await api(`/api/admin/coaching/members/${encodeURIComponent(state.memberId)}`);
    const summary = payload.coaching || {};
    $('coachingMemberSummary').textContent = summaryText(summary);
    for (const value of Object.values(summary.latestMeasurements || {})) {
      const row = document.createElement('div');
      row.textContent = `${value.metricKey}: ${value.value} ${value.unit}`;
      box.appendChild(row);
    }
    for (const goal of (summary.goals || []).filter((item) => item.status === 'active')) {
      const row = document.createElement('div');
      row.textContent = `Goal · ${goal.metricKey}: ${goal.targetValue} ${goal.unit}`;
      box.appendChild(row);
    }
    if (summary.currentDiet?.plan) {
      const row = document.createElement('div');
      row.textContent = `Nutrition · ${summary.currentDiet.plan.title} v${summary.currentDiet.plan.version}`;
      box.appendChild(row);
    }
    if (!box.children.length) box.textContent = 'No coaching records yet.';
  }

  async function loadTemplates() {
    const payload = await api('/api/admin/coaching/diets');
    state.templates = payload.templates || [];
    const select = $('dietTemplateSelect');
    const previous = select.value;
    select.replaceChildren();
    for (const template of state.templates) {
      const option = document.createElement('option');
      option.value = template.id;
      option.textContent = `${template.name} · ${template.status} · v${template.latestVersion || 0}`;
      select.appendChild(option);
    }
    if (previous && state.templates.some((item) => item.id === previous)) select.value = previous;
    await loadVersions();
  }

  async function loadVersions() {
    const template = selectedTemplate();
    state.versions = [];
    if (!template) {
      $('dietTemplateStatus').textContent = 'Create a template before adding a version.';
      return;
    }
    const payload = await api(`/api/admin/coaching/diets/${encodeURIComponent(template.id)}/versions`);
    state.versions = payload.versions || [];
    const latest = state.versions[0];
    $('dietTemplateStatus').textContent = `${template.status.toUpperCase()} · ${latest ? `latest version ${latest.version}` : 'no versions yet'} · General fitness nutrition only.`;
  }

  async function addMeasurement() {
    if (!selectedMember()) return;
    try {
      await api(`/api/admin/coaching/members/${encodeURIComponent(selectedMember())}/measurements`, {
        method: 'POST', body: {
          metricKey: $('coachingMetric').value,
          value: Number($('coachingValue').value),
        },
      });
      $('coachingValue').value = '';
      flash('Progress measurement recorded.');
      await renderMember();
    } catch (error) { flash(error.message, 'error'); }
  }

  async function addGoal() {
    if (!selectedMember()) return;
    try {
      await api(`/api/admin/coaching/members/${encodeURIComponent(selectedMember())}/goals`, {
        method: 'POST', body: {
          metricKey: $('goalMetric').value,
          targetValue: Number($('goalValue').value),
        },
      });
      $('goalValue').value = '';
      flash('Coaching goal set.');
      await renderMember();
    } catch (error) { flash(error.message, 'error'); }
  }

  function mealItems(id) {
    return $(id).value.split(',').map((item) => item.trim()).filter(Boolean);
  }

  async function createTemplate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await api('/api/admin/coaching/diets', {
        method: 'POST', body: {
          code: $('dietCode').value,
          name: $('dietName').value,
          description: $('dietDescription').value || null,
        },
      });
      form.reset();
      flash('Nutrition template created as an inactive draft.');
      await loadTemplates();
    } catch (error) { flash(error.message, 'error'); }
  }

  async function createVersion(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const template = selectedTemplate();
    if (!template) return;
    try {
      const meals = [
        ['Breakfast', mealItems('dietBreakfast')],
        ['Lunch', mealItems('dietLunch')],
        ['Dinner', mealItems('dietDinner')],
      ].filter((entry) => entry[1].length).map(([name, items]) => ({ name, items }));
      await api(`/api/admin/coaching/diets/${encodeURIComponent(template.id)}/versions`, {
        method: 'POST', body: {
          title: $('dietVersionTitle').value,
          content: {
            dietType: $('dietType').value,
            meals,
            notes: $('dietNotes').value ? [$('dietNotes').value] : [],
          },
        },
      });
      form.reset();
      flash('Immutable nutrition-plan version created.');
      await loadTemplates();
    } catch (error) { flash(error.message, 'error'); }
  }

  async function activateTemplate() {
    const template = selectedTemplate();
    if (!template) return;
    try {
      await api(`/api/admin/coaching/diets/${encodeURIComponent(template.id)}`, {
        method: 'PATCH', body: { status: 'active' },
      });
      flash('Nutrition template activated.');
      await loadTemplates();
    } catch (error) { flash(error.message, 'error'); }
  }

  async function assignLatest() {
    const memberId = selectedMember();
    const template = selectedTemplate();
    const latest = state.versions[0];
    if (!memberId || !template || !latest) return;
    if (template.status !== 'active') {
      flash('Activate the template before assigning it.', 'error');
      return;
    }
    try {
      await api(`/api/admin/coaching/members/${encodeURIComponent(memberId)}/diet`, {
        method: 'POST', body: {
          versionId: latest.id,
          note: 'Assigned from Gravity Control Room',
        },
      });
      flash('Latest nutrition-plan version assigned.');
      await renderMember();
    } catch (error) { flash(error.message, 'error'); }
  }

  async function renderWorkspace() {
    if (!state.admin) await syncAdmin();
    if (!canCoach()) return;
    await Promise.all([loadMembers(), loadTemplates()]);
    await renderMember();
  }

  $('coachingMember').addEventListener('change', () => {
    renderMember().catch((error) => flash(error.message, 'error'));
  });
  $('dietTemplateSelect').addEventListener('change', () => {
    loadVersions().catch((error) => flash(error.message, 'error'));
  });
  $('addMeasurement').addEventListener('click', addMeasurement);
  $('addGoal').addEventListener('click', addGoal);
  $('dietTemplateForm').addEventListener('submit', createTemplate);
  $('dietVersionForm').addEventListener('submit', createVersion);
  $('activateDietTemplate').addEventListener('click', activateTemplate);
  $('assignDietVersion').addEventListener('click', assignLatest);

  window.GravityCoachingAdmin = {
    setAdmin(admin) {
      state.admin = admin;
      $('coachingNav').hidden = !canCoach();
    },
    renderWorkspace() {
      return renderWorkspace().catch((error) => {
        flash(error.message, 'error');
        throw error;
      });
    },
  };

  const app = $('app');
  const observer = new MutationObserver(() => {
    if (!app.hidden) syncAdmin().catch(() => {});
  });
  observer.observe(app, { attributes: true, attributeFilter: ['hidden'] });
  syncAdmin().catch(() => {});
})();
