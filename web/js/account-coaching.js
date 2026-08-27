(() => {
  'use strict';

  const signedIn = document.getElementById('account-signed-in');
  const profileForm = document.getElementById('profile-form');
  if (!signedIn || !profileForm) return;

  const labels = {
    weight_kg: 'Weight', body_fat_pct: 'Body fat', waist_cm: 'Waist',
    chest_cm: 'Chest', arm_cm: 'Arm', hip_cm: 'Hip',
  };
  const card = document.createElement('section');
  card.className = 'membership-card';
  card.id = 'coaching-card';
  card.hidden = true;
  card.innerHTML = '<div class="membership-card-head"><div><span class="membership-label">COACHING</span><h3>Your progress & nutrition plan</h3></div></div>' +
    '<p class="membership-muted">Progress records are entered by authorized Gravity staff. Nutrition plans are general fitness guidance, not medical advice.</p>' +
    '<div id="coaching-measurements" class="membership-history"></div>' +
    '<div id="coaching-goals" class="membership-history"></div>' +
    '<div id="coaching-diet" class="membership-history"></div>';
  signedIn.insertBefore(card, profileForm);

  const measurementBox = card.querySelector('#coaching-measurements');
  const goalsBox = card.querySelector('#coaching-goals');
  const dietBox = card.querySelector('#coaching-diet');

  function formatDate(value) {
    if (!value) return '—';
    const date = new Date(Number(value) * 1000);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString();
  }

  function item(title, detail, small = '') {
    const row = document.createElement('div');
    row.className = 'membership-history-item';
    const strong = document.createElement('strong'); strong.textContent = title;
    const span = document.createElement('span'); span.textContent = detail;
    row.append(strong, span);
    if (small) {
      const note = document.createElement('small'); note.textContent = small;
      row.appendChild(note);
    }
    return row;
  }

  function empty(box, message) {
    box.replaceChildren();
    const node = document.createElement('div');
    node.className = 'membership-muted';
    node.textContent = message;
    box.appendChild(node);
  }

  function renderMeasurements(latest) {
    measurementBox.replaceChildren();
    const entries = Object.values(latest || {});
    if (!entries.length) return empty(measurementBox, 'No progress measurements have been recorded yet.');
    for (const value of entries) {
      measurementBox.appendChild(item(
        labels[value.metricKey] || value.metricKey,
        `${value.value} ${value.unit}`,
        `Recorded ${formatDate(value.measuredAt)}`,
      ));
    }
  }

  function renderGoals(goals) {
    goalsBox.replaceChildren();
    const active = (goals || []).filter((goal) => goal.status === 'active');
    if (!active.length) return empty(goalsBox, 'No active coaching goals are set.');
    for (const goal of active) {
      const due = goal.targetAt ? ` · target ${formatDate(goal.targetAt)}` : '';
      goalsBox.appendChild(item(
        `${labels[goal.metricKey] || goal.metricKey} goal`,
        `${goal.targetValue} ${goal.unit}${due}`,
        'Goals are coaching targets, not medical targets.',
      ));
    }
  }

  function renderDiet(current, disclaimer) {
    dietBox.replaceChildren();
    if (!current?.plan) return empty(dietBox, 'No nutrition plan is currently assigned.');
    const plan = current.plan;
    dietBox.appendChild(item(
      plan.title || 'Assigned nutrition plan',
      `${String(plan.content?.dietType || '').replaceAll('_', ' ')} · version ${plan.version}`,
      `Assigned ${formatDate(current.startsAt)}`,
    ));
    for (const meal of plan.content?.meals || []) {
      dietBox.appendChild(item(meal.name, (meal.items || []).join(' · ')));
    }
    const note = document.createElement('div');
    note.className = 'membership-muted';
    note.textContent = plan.disclaimer || disclaimer || 'General nutrition guidance only; not medical advice.';
    dietBox.appendChild(note);
  }

  function render(coaching) {
    renderMeasurements(coaching.latestMeasurements);
    renderGoals(coaching.goals);
    renderDiet(coaching.currentDiet, coaching.nutritionDisclaimer);
    card.hidden = false;
  }

  async function refresh() {
    if (signedIn.hidden) return;
    try {
      const response = await fetch('/api/me/coaching', {
        credentials: 'same-origin', headers: { Accept: 'application/json' },
      });
      if (response.status === 401) { card.hidden = true; return; }
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
      render(payload.coaching || {});
    } catch (_) {
      empty(measurementBox, 'Coaching data is temporarily unavailable. No account data was changed.');
      goalsBox.replaceChildren();
      dietBox.replaceChildren();
      card.hidden = false;
    }
  }

  const observer = new MutationObserver(() => {
    if (!signedIn.hidden) refresh();
    else card.hidden = true;
  });
  observer.observe(signedIn, { attributes: true, attributeFilter: ['hidden'] });
  if (!signedIn.hidden) refresh();
})();
