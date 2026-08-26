const FIREBASE_SDK_VERSION = '12.18.0';
const states = Array.from(document.querySelectorAll('.account-state'));
const signedOutStatus = document.getElementById('signed-out-status');
const signedInStatus = document.getElementById('signed-in-status');
let firebaseApi = null;
let firebaseAuth = null;
let firebaseConfig = null;
let phoneConfirmation = null;
let recaptchaVerifier = null;

function showState(id) {
  states.forEach((state) => { state.hidden = state.id !== id; });
}

function setStatus(element, message, tone = '') {
  element.textContent = message;
  element.dataset.tone = tone;
  if (tone === 'error') element.focus({ preventScroll: false });
}

function setBusy(form, busy, label) {
  Array.from(form.elements).forEach((element) => { element.disabled = busy; });
  const submit = form.querySelector('[type="submit"]');
  if (!submit) return;
  if (!submit.dataset.label) submit.dataset.label = submit.textContent;
  submit.textContent = busy ? label : submit.dataset.label;
}

function cookieValue(name) {
  const prefix = `${name}=`;
  const item = document.cookie.split(';').map((part) => part.trim()).find((part) => part.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : '';
}

async function jsonRequest(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json', ...(options.headers || {}) },
    ...options
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || 'request_failed');
    error.code = payload.error || 'request_failed';
    error.status = response.status;
    error.fields = payload.fields || {};
    throw error;
  }
  return payload;
}

function friendlyError(error) {
  if (error && (error.code === 'account_disabled' || error.code === 'auth/user-disabled')) {
    return 'This account is unavailable. Please contact Gravity Fitness for help.';
  }
  if (error && (error.code === 'account_link_required' || error.code === 'account_conflict')) {
    return 'That verified email or mobile is already linked. Sign in to the existing account or contact support.';
  }
  if (error && error.code === 'rate_limited') return 'Too many attempts. Please wait and try again.';
  if (error && error.code === 'authentication_unavailable') return 'Member accounts are temporarily unavailable.';
  if (error && error.code === 'invalid_csrf') return 'Your security token expired. Reload the page and try again.';
  if (error && error.code && error.code.startsWith('auth/')) {
    return 'We could not verify those details. Check them and try again.';
  }
  return 'Something went wrong. Your changes were not assumed successful; please try again.';
}

function selectMode() {
  const mode = new URLSearchParams(window.location.search).get('mode') === 'register' ? 'register' : 'login';
  const login = document.getElementById('login-form');
  const register = document.getElementById('register-form');
  login.hidden = mode !== 'login';
  register.hidden = mode !== 'register';
  document.getElementById('mode-login').toggleAttribute('aria-current', mode === 'login');
  document.getElementById('mode-register').toggleAttribute('aria-current', mode === 'register');
}

async function loadFirebase() {
  if (firebaseApi) return;
  const base = `https://www.gstatic.com/firebasejs/${FIREBASE_SDK_VERSION}`;
  const [appModule, authModule] = await Promise.all([
    import(`${base}/firebase-app.js`),
    import(`${base}/firebase-auth.js`)
  ]);
  const app = appModule.initializeApp(firebaseConfig);
  firebaseAuth = authModule.getAuth(app);
  await authModule.setPersistence(firebaseAuth, authModule.inMemoryPersistence);
  firebaseApi = authModule;
}

async function exchangeFirebaseUser(user) {
  const idToken = await user.getIdToken(true);
  try {
    return await jsonRequest('/api/auth/session', {
      method: 'POST',
      headers: { Authorization: `Bearer ${idToken}` },
      body: ''
    });
  } finally {
    await firebaseApi.signOut(firebaseAuth).catch(() => {});
  }
}

function renderUser(user) {
  showState('account-signed-in');
  document.getElementById('member-heading').textContent = user.profileComplete ? 'Your member account' : 'Complete your profile';
  document.getElementById('member-email').textContent = user.email || 'Not linked';
  document.getElementById('member-phone').textContent = user.phone || 'Not linked';
  document.getElementById('member-profile-state').textContent = user.profileComplete ? 'Complete' : 'Incomplete';
  document.getElementById('profile-name').value = user.displayName || '';
  const profile = user.profile || {};
  document.getElementById('profile-birth').value = profile.dateOfBirth || '';
  document.getElementById('profile-gender').value = profile.gender || '';
  document.getElementById('profile-address').value = profile.address || '';
  document.getElementById('profile-emergency-name').value = profile.emergencyContactName || '';
  document.getElementById('profile-emergency-phone').value = profile.emergencyContactPhone || '';
  document.getElementById('profile-health').value = profile.healthNotes || '';
}

async function refreshSession() {
  return jsonRequest('/api/auth/session');
}

async function initializeAccount() {
  showState('account-checking');
  setStatus(signedOutStatus, '');
  setStatus(signedInStatus, '');
  try {
    const [config, session] = await Promise.all([
      jsonRequest('/api/auth/config'),
      refreshSession()
    ]);
    if (session.authenticated) {
      renderUser(session.user);
      return;
    }
    if (!config.enabled || !config.firebase) {
      showState('account-unavailable');
      return;
    }
    firebaseConfig = config.firebase;
    await loadFirebase();
    selectMode();
    showState('account-signed-out');
  } catch (error) {
    showState('account-unavailable');
  }
}

document.getElementById('account-retry').addEventListener('click', initializeAccount);

document.getElementById('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  setBusy(form, true, 'Signing in…');
  setStatus(signedOutStatus, 'Verifying your account…');
  try {
    const credential = await firebaseApi.signInWithEmailAndPassword(
      firebaseAuth,
      document.getElementById('login-email').value.trim(),
      document.getElementById('login-password').value
    );
    if (!credential.user.emailVerified) {
      await firebaseApi.sendEmailVerification(credential.user).catch(() => {});
      await firebaseApi.signOut(firebaseAuth);
      showState('account-verification');
      return;
    }
    const result = await exchangeFirebaseUser(credential.user);
    renderUser(result.user);
  } catch (error) {
    setStatus(signedOutStatus, friendlyError(error), 'error');
  } finally {
    setBusy(form, false, '');
  }
});

document.getElementById('register-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const password = document.getElementById('register-password');
  const confirmation = document.getElementById('register-confirm');
  confirmation.setCustomValidity(password.value === confirmation.value ? '' : 'Passwords must match');
  if (!form.reportValidity()) return;
  setBusy(form, true, 'Creating account…');
  setStatus(signedOutStatus, 'Creating your Firebase identity…');
  try {
    const credential = await firebaseApi.createUserWithEmailAndPassword(
      firebaseAuth,
      document.getElementById('register-email').value.trim(),
      password.value
    );
    await firebaseApi.updateProfile(credential.user, {
      displayName: document.getElementById('register-name').value.trim()
    });
    await firebaseApi.sendEmailVerification(credential.user);
    await firebaseApi.signOut(firebaseAuth);
    showState('account-verification');
  } catch (error) {
    setStatus(signedOutStatus, friendlyError(error), 'error');
  } finally {
    setBusy(form, false, '');
  }
});

document.getElementById('forgot-password').addEventListener('click', async () => {
  const email = document.getElementById('login-email');
  if (!email.checkValidity()) {
    email.reportValidity();
    return;
  }
  setStatus(signedOutStatus, 'Requesting a reset link…');
  try {
    await firebaseApi.sendPasswordResetEmail(firebaseAuth, email.value.trim());
    setStatus(signedOutStatus, 'If that email can receive a reset link, Firebase has sent it.', 'success');
  } catch (error) {
    if (error.code === 'auth/user-not-found') {
      setStatus(signedOutStatus, 'If that email can receive a reset link, Firebase has sent it.', 'success');
    } else {
      setStatus(signedOutStatus, friendlyError(error), 'error');
    }
  }
});

document.getElementById('google-sign-in').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  setStatus(signedOutStatus, 'Opening Google sign-in…');
  try {
    const credential = await firebaseApi.signInWithPopup(firebaseAuth, new firebaseApi.GoogleAuthProvider());
    const result = await exchangeFirebaseUser(credential.user);
    renderUser(result.user);
  } catch (error) {
    setStatus(signedOutStatus, friendlyError(error), 'error');
  } finally {
    button.disabled = false;
  }
});

document.getElementById('phone-sign-in-toggle').addEventListener('click', () => {
  const form = document.getElementById('phone-form');
  form.hidden = !form.hidden;
  if (!form.hidden) document.getElementById('phone-number').focus();
});

document.getElementById('phone-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  setBusy(form, true, 'Sending code…');
  setStatus(signedOutStatus, 'Requesting mobile verification…');
  try {
    if (!recaptchaVerifier) {
      recaptchaVerifier = new firebaseApi.RecaptchaVerifier(firebaseAuth, 'recaptcha-container', { size: 'invisible' });
    }
    phoneConfirmation = await firebaseApi.signInWithPhoneNumber(
      firebaseAuth,
      document.getElementById('phone-number').value.trim(),
      recaptchaVerifier
    );
    document.getElementById('phone-code-wrap').hidden = false;
    setStatus(signedOutStatus, 'Enter the verification code sent to your mobile.', 'success');
    document.getElementById('phone-code').focus();
  } catch (error) {
    if (recaptchaVerifier) { recaptchaVerifier.clear(); recaptchaVerifier = null; }
    setStatus(signedOutStatus, friendlyError(error), 'error');
  } finally {
    setBusy(form, false, '');
  }
});

document.getElementById('confirm-phone-code').addEventListener('click', async (event) => {
  const code = document.getElementById('phone-code');
  if (!phoneConfirmation || !code.checkValidity() || !code.value) {
    code.reportValidity();
    return;
  }
  event.currentTarget.disabled = true;
  setStatus(signedOutStatus, 'Verifying the code…');
  try {
    const credential = await phoneConfirmation.confirm(code.value);
    const result = await exchangeFirebaseUser(credential.user);
    renderUser(result.user);
  } catch (error) {
    setStatus(signedOutStatus, friendlyError(error), 'error');
  } finally {
    event.currentTarget.disabled = false;
  }
});

document.getElementById('profile-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  setBusy(form, true, 'Saving…');
  setStatus(signedInStatus, 'Saving your profile…');
  const fields = new FormData(form);
  const payload = Object.fromEntries(fields.entries());
  try {
    await jsonRequest('/api/me', {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': cookieValue('gravity_csrf') || cookieValue('__Host-gravity_csrf')
      },
      body: JSON.stringify(payload)
    });
    const confirmed = await jsonRequest('/api/me');
    renderUser(confirmed.user);
    setStatus(signedInStatus, 'Profile saved and confirmed.', 'success');
  } catch (error) {
    if (error.status === 401 || error.code === 'account_disabled') return initializeAccount();
    setStatus(signedInStatus, friendlyError(error), 'error');
  } finally {
    setBusy(form, false, '');
  }
});

async function logout(allDevices) {
  setStatus(signedInStatus, allDevices ? 'Signing out all devices…' : 'Signing out…');
  try {
    await jsonRequest(allDevices ? '/api/auth/logout-all' : '/api/auth/logout', {
      method: 'POST',
      headers: { 'X-CSRF-Token': cookieValue('gravity_csrf') || cookieValue('__Host-gravity_csrf') },
      body: ''
    });
    await initializeAccount();
  } catch (error) {
    setStatus(signedInStatus, friendlyError(error), 'error');
  }
}

document.getElementById('logout-button').addEventListener('click', () => logout(false));
document.getElementById('logout-all-button').addEventListener('click', () => logout(true));

const menu = document.getElementById('mobile-nav');
const menuButton = document.getElementById('account-menu-button');
function setMenu(open) {
  menu.classList.toggle('open', open);
  menuButton.setAttribute('aria-expanded', String(open));
  document.body.style.overflow = open ? 'hidden' : '';
}
menuButton.addEventListener('click', () => setMenu(true));
document.getElementById('account-menu-close').addEventListener('click', () => setMenu(false));

initializeAccount();
