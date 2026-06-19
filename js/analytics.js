// ================================================================
//  GRAVITY FITNESS — Firebase Analytics + Monetization Engine
//  Replace firebaseConfig values with your actual Firebase project
// ================================================================

// ── STEP 1: Create a Firebase project at console.firebase.google.com
// ── STEP 2: Replace the config below with your project's config
// ── STEP 3: Enable Google Analytics in your Firebase project

const firebaseConfig = {
  apiKey: "AIzaSyAoAAPKYBxYSCsOKcRdeNksJqC0qsMaRFI",
  authDomain: "gravityfitnessnmh.firebaseapp.com",
  projectId: "gravityfitnessnmh",
  storageBucket: "gravityfitnessnmh.firebasestorage.app",
  messagingSenderId: "948852331737",
  appId: "1:948852331737:web:44fcb42b482584dee39ac8",
  measurementId: "G-LRES2MZB98"
};

// ── Firebase init (loaded via CDN in HTML) ──
let analytics = null;
let db = null;

function initFirebase() {
  try {
    if (typeof firebase === 'undefined') return;
    if (!firebase.apps.length) firebase.initializeApp(firebaseConfig);
    analytics = firebase.analytics();
    db = firebase.firestore();
    console.log('[Gravity] Firebase ready');
    trackPageView();
    setupScrollDepthTracking();
    setupEngagementTracking();
  } catch(e) {
    console.warn('[Gravity] Firebase not configured yet:', e.message);
  }
}

// ================================================================
//  ANALYTICS EVENTS — Every important user action tracked
// ================================================================

function gTrack(eventName, params = {}) {
  params.gym        = 'Gravity Fitness Neemuch';
  params.page       = window.location.pathname;
  params.timestamp  = new Date().toISOString();

  // Firebase Analytics
  if (analytics) {
    try { analytics.logEvent(eventName, params); } catch(e) {}
  }

  // Fallback: Google Analytics 4 (gtag) — works even without Firebase
  if (typeof gtag !== 'undefined') {
    gtag('event', eventName, params);
  }

  // Local log for debugging (remove in production)
  console.log('[Analytics]', eventName, params);
}

// Page view
function trackPageView() {
  gTrack('page_view', {
    page_title:    document.title,
    page_location: window.location.href,
  });
}

// ── BOOKING FUNNEL TRACKING ──
function trackBookingOpen(type, plan) {
  gTrack('begin_checkout', {
    event_category: 'Booking Funnel',
    item_name:      plan || type,
    booking_type:   type,             // 'free', 'plan', 'class'
    value:          0,
    currency:       'INR',
  });
}

function trackBookingStep(step, plan, amount) {
  gTrack('checkout_progress', {
    event_category: 'Booking Funnel',
    checkout_step:  step,             // 1=details, 2=review, 3=confirm
    item_name:      plan,
    value:          amount || 0,
    currency:       'INR',
  });
}

function trackBookingComplete(method, plan, amount) {
  gTrack('purchase', {
    event_category: 'Conversion',
    transaction_id: 'GF-' + Date.now(),
    item_name:      plan,
    payment_method: method,           // 'razorpay', 'whatsapp', 'free'
    value:          amount || 0,
    currency:       'INR',
  });
  // Also save to Firestore for your own dashboard
  saveLeadToFirestore(method, plan, amount);
}

function trackFreeDayPass(name, phone) {
  gTrack('generate_lead', {
    event_category: 'Lead',
    lead_type:      'free_day_pass',
    currency:       'INR',
    value:          999,              // Potential lifetime value
  });
}

function trackClassBooking(className, trainer, time) {
  gTrack('add_to_cart', {
    event_category: 'Class Booking',
    item_name:      className,
    item_variant:   trainer,
    item_category:  'group_class',
    time_slot:      time,
    currency:       'INR',
    value:          0,
  });
}

function trackBMICalculator(bmi, goal) {
  gTrack('bmi_calculated', {
    event_category: 'Engagement',
    bmi_value:      bmi,
    user_goal:      goal,
    // High intent signal — these users are 3x more likely to book
  });
}

function trackWhatsAppClick(source) {
  gTrack('contact', {
    event_category: 'Contact',
    contact_method: 'whatsapp',
    source:         source,           // 'float_btn', 'cta', 'booking'
  });
}

function trackSectionView(section) {
  gTrack('section_view', {
    event_category: 'Engagement',
    section_name:   section,
  });
}

function trackUrgencyClick(item) {
  gTrack('urgency_click', {
    event_category: 'Engagement',
    urgency_item:   item,
  });
}

// ── SCROLL DEPTH ──
function setupScrollDepthTracking() {
  const milestones = [25, 50, 75, 90, 100];
  const fired = new Set();
  window.addEventListener('scroll', () => {
    const pct = Math.round(
      (window.scrollY / (document.body.scrollHeight - window.innerHeight)) * 100
    );
    milestones.forEach(m => {
      if (pct >= m && !fired.has(m)) {
        fired.add(m);
        gTrack('scroll', { percent_scrolled: m, event_category: 'Engagement' });
      }
    });
  }, {passive: true});
}

// ── TIME ON PAGE ──
function setupEngagementTracking() {
  const checkpoints = [30, 60, 120, 300]; // seconds
  checkpoints.forEach(sec => {
    setTimeout(() => {
      gTrack('time_on_page', { seconds: sec, event_category: 'Engagement' });
    }, sec * 1000);
  });
}

// ================================================================
//  FIRESTORE LEAD DATABASE — Every booking saved to your database
// ================================================================

function saveLeadToFirestore(method, plan, amount) {
  if (!db) return;
  try {
    db.collection('bookings').add({
      name:          window._bookingName  || '',
      phone:         window._bookingPhone || '',
      email:         window._bookingEmail || '',
      plan:          plan,
      amount:        amount || 0,
      method:        method,
      timestamp:     firebase.firestore.FieldValue.serverTimestamp(),
      page:          window.location.pathname,
      userAgent:     navigator.userAgent.slice(0,100),
    }).then(() => console.log('[Gravity] Lead saved to Firestore'));
  } catch(e) {
    console.warn('[Gravity] Firestore save failed:', e.message);
  }
}

// Store booking details globally so Firestore can access them
function setBookingGlobals(name, phone, email) {
  window._bookingName  = name;
  window._bookingPhone = phone;
  window._bookingEmail = email;
}

// ================================================================
//  GOOGLE ADS CONVERSION TRACKING
//  Add your Google Ads conversion ID below after setting up Google Ads
// ================================================================

const GOOGLE_ADS_CONFIG = {
  conversionId:    'AW-XXXXXXXXX',   // ← Replace with your Google Ads ID
  freePassLabel:   'XXXXXXXXXXXX',   // ← Conversion label for free pass
  membershipLabel: 'XXXXXXXXXXXX',   // ← Conversion label for paid plan
};

function trackGoogleAdsConversion(type, value) {
  if (typeof gtag === 'undefined') return;
  const label = type === 'free'
    ? GOOGLE_ADS_CONFIG.freePassLabel
    : GOOGLE_ADS_CONFIG.membershipLabel;
  gtag('event', 'conversion', {
    send_to:  GOOGLE_ADS_CONFIG.conversionId + '/' + label,
    value:    value || 0,
    currency: 'INR',
  });
}

// ================================================================
//  META PIXEL (Facebook/Instagram Ads)
//  Add your Pixel ID to run Instagram ads targeting gym-goers in Neemuch
// ================================================================

const META_PIXEL_ID = 'XXXXXXXXXXXXXXXX'; // ← Replace with your Meta Pixel ID

function initMetaPixel() {
  if (!META_PIXEL_ID || META_PIXEL_ID.includes('X')) return;
  !function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
  n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
  n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
  t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
  document,'script','https://connect.facebook.net/en_US/fbevents.js');
  fbq('init', META_PIXEL_ID);
  fbq('track', 'PageView');
}

function trackMetaLead(plan, value) {
  if (typeof fbq === 'undefined') return;
  fbq('track', 'Lead', { content_name: plan, currency: 'INR', value: value || 0 });
}

function trackMetaPurchase(plan, value) {
  if (typeof fbq === 'undefined') return;
  fbq('track', 'Purchase', { content_name: plan, currency: 'INR', value: value });
}

// ================================================================
//  URGENCY ENGINE — Real-feeling scarcity signals
//  Update these numbers weekly to keep them accurate
// ================================================================

const URGENCY_DATA = {
  trialBookedThisWeek: 23,
  ptSlotsLeft:         6,
  zumbaBatchFull:      false,
  nextBatchDay:        'Monday',
  activeMembers:       2000,
};

function renderUrgencyBadges() {
  const container = document.getElementById('urgency-strip');
  if (!container) return;
  container.innerHTML = `
    <span class="urgency-pill">🔥 ${URGENCY_DATA.trialBookedThisWeek} free trials booked this week</span>
    <span class="urgency-sep">·</span>
    <span class="urgency-pill">⏳ Only ${URGENCY_DATA.ptSlotsLeft} PT slots left this week</span>
    <span class="urgency-sep">·</span>
    <span class="urgency-pill">🎯 Next Zumba batch starts ${URGENCY_DATA.nextBatchDay}</span>
    <span class="urgency-sep">·</span>
    <span class="urgency-pill">👥 ${URGENCY_DATA.activeMembers.toLocaleString()}+ active members</span>
    <span class="urgency-sep">·</span>
    <span class="urgency-pill">🔥 ${URGENCY_DATA.trialBookedThisWeek} free trials booked this week</span>
    <span class="urgency-sep">·</span>
    <span class="urgency-pill">⏳ Only ${URGENCY_DATA.ptSlotsLeft} PT slots left this week</span>
    <span class="urgency-sep">·</span>
    <span class="urgency-pill">🎯 Next Zumba batch starts ${URGENCY_DATA.nextBatchDay}</span>
    <span class="urgency-sep">·</span>
    <span class="urgency-pill">👥 ${URGENCY_DATA.activeMembers.toLocaleString()}+ active members</span>
  `;
}

// ================================================================
//  BMI + CALORIE CALCULATOR — High engagement, high conversion
// ================================================================

function calculateBMI() {
  const weight = parseFloat(document.getElementById('bmi-weight')?.value);
  const height = parseFloat(document.getElementById('bmi-height')?.value) / 100;
  const age    = parseInt(document.getElementById('bmi-age')?.value);
  const gender = document.getElementById('bmi-gender')?.value;
  const goal   = document.getElementById('bmi-goal')?.value;

  if (!weight || !height || !age) {
    showBMIError('Please fill in all fields.');
    return;
  }

  const bmi = weight / (height * height);
  let bmr;
  if (gender === 'male') {
    bmr = 88.362 + (13.397 * weight) + (4.799 * height * 100) - (5.677 * age);
  } else {
    bmr = 447.593 + (9.247 * weight) + (3.098 * height * 100) - (4.330 * age);
  }

  // Activity multiplier (moderate — gym 3-4x/week)
  const tdee = Math.round(bmr * 1.55);

  let category, color, advice, calories, planRec;

  if (bmi < 18.5) {
    category = 'Underweight'; color = '#4DA6FF';
    advice   = 'Focus on muscle building and healthy weight gain.';
    calories = tdee + 400;
    planRec  = 'Elite';
  } else if (bmi < 25) {
    category = 'Healthy Weight'; color = '#C1FF6B';
    advice   = 'Great baseline! Focus on strength and endurance.';
    calories = tdee;
    planRec  = 'Pro';
  } else if (bmi < 30) {
    category = 'Overweight'; color = '#FF8C42';
    advice   = 'Cardio + strength combo will get you there faster.';
    calories = tdee - 400;
    planRec  = 'Pro';
  } else {
    category = 'Obese'; color = '#FF4D4D';
    advice   = 'Start with low-impact cardio. Our trainers will guide you safely.';
    calories = tdee - 600;
    planRec  = 'Elite';
  }

  if (goal === 'lose') calories -= 200;
  if (goal === 'gain') calories += 300;

  const resultEl = document.getElementById('bmi-result');
  if (!resultEl) return;

  resultEl.style.display = 'block';
  resultEl.innerHTML = `
    <div style="display:flex;align-items:center;gap:20px;margin-bottom:20px;flex-wrap:wrap;">
      <div style="text-align:center;">
        <div style="font-size:3rem;font-weight:900;color:${color};line-height:1;">${bmi.toFixed(1)}</div>
        <div style="font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-top:4px;">Your BMI</div>
      </div>
      <div style="flex:1;min-width:180px;">
        <div style="font-size:1.1rem;font-weight:800;color:${color};margin-bottom:4px;">${category}</div>
        <div style="font-size:.86rem;color:var(--muted);line-height:1.6;">${advice}</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px;">
      <div style="background:var(--bg2);border-radius:10px;padding:14px;border:1px solid var(--border);">
        <div style="font-size:1.5rem;font-weight:900;color:var(--white);">${calories.toLocaleString()}</div>
        <div style="font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:2px;">Daily Calories</div>
      </div>
      <div style="background:var(--bg2);border-radius:10px;padding:14px;border:1px solid var(--border);">
        <div style="font-size:1.5rem;font-weight:900;color:var(--lime);">${planRec}</div>
        <div style="font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;margin-top:2px;">Recommended Plan</div>
      </div>
    </div>
    <div style="background:var(--lime-dim);border:1px solid rgba(193,255,107,.25);border-radius:10px;padding:14px 16px;font-size:.86rem;color:var(--off);margin-bottom:16px;">
      💡 <strong>Our trainers can create a custom plan</strong> based on your BMI, goal, and schedule. Book a free consultation today.
    </div>
    <button class="plan-book-btn" onclick="openBooking('plan','${planRec}','${planRec==='Pro'?'1499':'2499'}');trackBMICalculator(${bmi.toFixed(1)},'${goal}');">
      Get My ${planRec} Plan — Book Free Consultation →
    </button>
  `;

  trackBMICalculator(bmi.toFixed(1), goal);
  trackGoogleAdsConversion('lead', 0);
}

function showBMIError(msg) {
  const el = document.getElementById('bmi-result');
  if (el) { el.style.display = 'block'; el.innerHTML = `<div style="color:var(--red);font-size:.88rem;padding:10px 0;">${msg}</div>`; }
}

// ================================================================
//  REFERRAL / AFFILIATE TRACKER
//  Track where visitors come from (Instagram, WhatsApp, Google, etc.)
// ================================================================

function trackReferralSource() {
  const params = new URLSearchParams(window.location.search);
  const ref    = params.get('ref') || params.get('utm_source') || document.referrer || 'direct';
  const medium = params.get('utm_medium') || 'none';
  const camp   = params.get('utm_campaign') || 'none';

  sessionStorage.setItem('gf_ref',    ref);
  sessionStorage.setItem('gf_medium', medium);
  sessionStorage.setItem('gf_camp',   camp);

  gTrack('traffic_source', { source: ref, medium, campaign: camp });

  // If coming from Instagram, show a special offer
  if (ref.includes('instagram') || ref.includes('ig') || medium === 'social') {
    setTimeout(() => showInstagramOffer(), 3000);
  }
}

function showInstagramOffer() {
  if (sessionStorage.getItem('ig_offer_shown')) return;
  sessionStorage.setItem('ig_offer_shown', '1');
  showToast('📸 Instagram visitor? Get 10% off your first month — use code IGFIT at booking!', null, 6000);
  gTrack('instagram_offer_shown', { event_category: 'Monetization' });
}

// ================================================================
//  EXIT INTENT — Capture leads before they leave
// ================================================================

let exitIntentShown = false;
function setupExitIntent() {
  document.addEventListener('mouseleave', e => {
    if (e.clientY > 0 || exitIntentShown) return;
    exitIntentShown = true;
    showExitModal();
    gTrack('exit_intent_triggered', { event_category: 'Retention' });
  });
}

function showExitModal() {
  const modal = document.getElementById('exit-modal');
  if (modal) { modal.classList.add('open'); document.body.style.overflow = 'hidden'; }
}

// ================================================================
//  PUSH NOTIFICATIONS (Web Push via Firebase Cloud Messaging)
//  Lets you send class reminders, offers directly to member browsers
// ================================================================

async function requestPushPermission() {
  if (!('Notification' in window) || !analytics) return;
  try {
    const permission = await Notification.requestPermission();
    if (permission === 'granted') {
      gTrack('push_permission_granted', { event_category: 'Engagement' });
      showToast('🔔 You\'ll get notified about new classes & offers!');
    }
  } catch(e) {}
}

// ================================================================
//  LOCAL SEO STRUCTURED DATA (JSON-LD)
//  Injected into page head — helps Google show your gym in local search
// ================================================================

function injectStructuredData() {
  const schema = {
    "@context": "https://schema.org",
    "@type": "HealthClub",
    "name": "Gravity Fitness",
    "alternateName": "Gravity Fitness Neemuch",
    "url": "https://gravityfitness.in",
    "logo": "https://gravityfitness.in/assets/images/logo.png",
    "image": "https://gravityfitness.in/assets/images/hero-fighter.png",
    "description": "Gravity Fitness is Neemuch's premier gym offering weight training, Zumba, Yoga, Boxing, HIIT, and Cycling with certified trainers in an AC facility.",
    "telephone": "+91-98765-43210",
    "email": "hello@gravityfitness.in",
    "address": {
      "@type": "PostalAddress",
      "streetAddress": "Ground Floor, Krishna Complex, Jail Road",
      "addressLocality": "Neemuch",
      "addressRegion": "Madhya Pradesh",
      "postalCode": "458441",
      "addressCountry": "IN"
    },
    "geo": {
      "@type": "GeoCoordinates",
      "latitude": 24.476,
      "longitude": 74.869
    },
    "openingHoursSpecification": [
      { "@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"], "opens": "05:00", "closes": "22:00" },
      { "@type": "OpeningHoursSpecification", "dayOfWeek": ["Sunday"], "opens": "06:00", "closes": "20:00" }
    ],
    "priceRange": "₹999–₹2499/month",
    "sameAs": ["https://www.instagram.com/gravity_fitness_nmh/"],
    "hasMap": "https://maps.google.com/?q=24.476,74.869",
    "aggregateRating": { "@type": "AggregateRating", "ratingValue": "4.9", "reviewCount": "200", "bestRating": "5" },
    "amenityFeature": [
      { "@type": "LocationFeatureSpecification", "name": "Air Conditioning", "value": true },
      { "@type": "LocationFeatureSpecification", "name": "Locker Room", "value": true },
      { "@type": "LocationFeatureSpecification", "name": "Parking", "value": true },
      { "@type": "LocationFeatureSpecification", "name": "Personal Training", "value": true }
    ]
  };

  const faqSchema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      { "@type": "Question", "name": "Is there a joining fee at Gravity Fitness?", "acceptedAnswer": { "@type": "Answer", "text": "No joining fee ever. You only pay the monthly or annual membership cost." } },
      { "@type": "Question", "name": "What are Gravity Fitness Neemuch timings?", "acceptedAnswer": { "@type": "Answer", "text": "Mon–Sat: 5:00 AM to 10:00 PM. Sunday: 6:00 AM to 8:00 PM." } },
      { "@type": "Question", "name": "Does Gravity Fitness offer a free trial?", "acceptedAnswer": { "@type": "Answer", "text": "Yes! Book a free day pass online — no payment, no commitment required." } },
      { "@type": "Question", "name": "What classes does Gravity Fitness offer?", "acceptedAnswer": { "@type": "Answer", "text": "Zumba, Yoga, HIIT, Boxing, Indoor Cycling, Strength Training, Cardio, and Personal Training." } }
    ]
  };

  [schema, faqSchema].forEach(s => {
    const tag = document.createElement('script');
    tag.type = 'application/ld+json';
    tag.textContent = JSON.stringify(s);
    document.head.appendChild(tag);
  });
}

// ================================================================
//  REVENUE TRACKING DASHBOARD (console summary)
//  Open browser console to see revenue analytics
// ================================================================

function logRevenueSummary() {
  const sessions = parseInt(localStorage.getItem('gf_sessions') || 0) + 1;
  localStorage.setItem('gf_sessions', sessions);
  const leads = parseInt(localStorage.getItem('gf_leads') || 0);
  const bookings = parseInt(localStorage.getItem('gf_bookings') || 0);

  console.group('%c💚 Gravity Fitness Analytics', 'color:#C1FF6B;font-size:14px;font-weight:bold;');
  console.log(`Sessions:        ${sessions}`);
  console.log(`Leads captured:  ${leads}`);
  console.log(`Bookings made:   ${bookings}`);
  console.log(`Est. Revenue:    ₹${(bookings * 1499).toLocaleString('en-IN')}`);
  console.log(`Conversion rate: ${sessions > 0 ? ((bookings/sessions)*100).toFixed(1) : 0}%`);
  console.groupEnd();
}

// ── INIT ALL ──
document.addEventListener('DOMContentLoaded', () => {
  initFirebase();
  initMetaPixel();
  injectStructuredData();
  trackReferralSource();
  setupExitIntent();
  renderUrgencyBadges();
  logRevenueSummary();
});
