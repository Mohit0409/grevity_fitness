/**
 * ═══════════════════════════════════════════════════════════════
 *  GRAVITY FITNESS — Interactive Athlete Animation Engine v2.0
 *  Premium GSAP + SVG barbell curl character
 * ═══════════════════════════════════════════════════════════════
 */

(function () {
  'use strict';

  // ── Respect prefers-reduced-motion ──────────────────────────
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  // ── Constants ───────────────────────────────────────────────
  const CURL_DURATION = 1.5;
  const HOLD_DURATION = 0.3;

  // ── State ───────────────────────────────────────────────────
  const state = {
    curlCount  : 0,
    isAnimating: false,
    queue      : 0,
    tabHidden  : false,
    gsapLoaded : false,
  };

  // ── Audio (Web Audio API) ───────────────────────────────────
  let audioCtx = null;
  function ensureAudio() {
    if (!audioCtx) {
      try { audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }
      catch (e) {}
    }
  }
  function playClinkSound() {
    ensureAudio();
    if (!audioCtx) return;
    try {
      const osc  = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(880, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(380, audioCtx.currentTime + 0.18);
      gain.gain.setValueAtTime(0.15, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.2);
      osc.start(audioCtx.currentTime);
      osc.stop(audioCtx.currentTime + 0.22);
    } catch (e) {}
  }

  // ═══════════════════════════════════════════════════════════
  //  PREMIUM SVG ATHLETE — 200×420 viewBox, large & detailed
  // ═══════════════════════════════════════════════════════════
  // ═══════════════════════════════════════════════════════════
  //  REALISTIC SVG ATHLETE v5 — fully connected body, proper
  //  proportions, realistic face, barbell at rest position
  // ═══════════════════════════════════════════════════════════
  function buildAthleteSVG() {
    return `
<svg id="gf-athlete-svg" viewBox="0 0 160 380" xmlns="http://www.w3.org/2000/svg"
     style="overflow:visible;filter:drop-shadow(0 20px 50px rgba(0,0,0,.7))drop-shadow(0 4px 14px rgba(0,0,0,.5))">
<defs>
  <!-- SKIN: warm brown athletic tone with depth -->
  <linearGradient id="sk" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%"   stop-color="#cb8150"/>
    <stop offset="50%"  stop-color="#b56c38"/>
    <stop offset="100%" stop-color="#8c4a1e"/>
  </linearGradient>
  <linearGradient id="sk-side" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%"   stop-color="#7a3a14"/>
    <stop offset="40%"  stop-color="#b56c38"/>
    <stop offset="100%" stop-color="#cb8150"/>
  </linearGradient>
  <radialGradient id="sk-face" cx="45%" cy="35%" r="65%">
    <stop offset="0%"   stop-color="#d89060"/>
    <stop offset="60%"  stop-color="#b56c38"/>
    <stop offset="100%" stop-color="#8c4a1e"/>
  </radialGradient>
  <!-- Bicep round highlight -->
  <radialGradient id="bicL" cx="35%" cy="28%" r="60%">
    <stop offset="0%"   stop-color="#d49060"/>
    <stop offset="50%"  stop-color="#b56c38"/>
    <stop offset="100%" stop-color="#7a3a14"/>
  </radialGradient>
  <radialGradient id="bicR" cx="65%" cy="28%" r="60%">
    <stop offset="0%"   stop-color="#d49060"/>
    <stop offset="50%"  stop-color="#b56c38"/>
    <stop offset="100%" stop-color="#7a3a14"/>
  </radialGradient>
  <!-- Black outfit -->
  <linearGradient id="cloth" x1="0" y1="0" x2=".4" y2="1">
    <stop offset="0%"   stop-color="#2e2e2e"/>
    <stop offset="55%"  stop-color="#181818"/>
    <stop offset="100%" stop-color="#080808"/>
  </linearGradient>
  <linearGradient id="cloth2" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%"   stop-color="#252525"/>
    <stop offset="100%" stop-color="#0a0a0a"/>
  </linearGradient>
  <!-- Shorts -->
  <linearGradient id="shorts" x1="0" y1="0" x2=".2" y2="1">
    <stop offset="0%"   stop-color="#161616"/>
    <stop offset="100%" stop-color="#060606"/>
  </linearGradient>
  <!-- Shoe -->
  <linearGradient id="shoe" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%"   stop-color="#222"/>
    <stop offset="100%" stop-color="#080808"/>
  </linearGradient>
  <!-- Bar metal -->
  <linearGradient id="metal" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%"   stop-color="#d0d0d0"/>
    <stop offset="30%"  stop-color="#ffffff"/>
    <stop offset="70%"  stop-color="#a8a8a8"/>
    <stop offset="100%" stop-color="#686868"/>
  </linearGradient>
  <!-- Plate -->
  <linearGradient id="plate" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%"   stop-color="#a0a0a0"/>
    <stop offset="45%"  stop-color="#cccccc"/>
    <stop offset="100%" stop-color="#585858"/>
  </linearGradient>
  <!-- Lime accent -->
  <linearGradient id="lime" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%"   stop-color="#d8ff7c"/>
    <stop offset="100%" stop-color="#88b818"/>
  </linearGradient>
  <!-- Hair -->
  <linearGradient id="hair" x1="0" y1="0" x2=".3" y2="1">
    <stop offset="0%"   stop-color="#0c0c0c"/>
    <stop offset="100%" stop-color="#1e1e1e"/>
  </linearGradient>
  <!-- Ground shadow -->
  <radialGradient id="gshadow" cx="50%" cy="50%" r="50%">
    <stop offset="0%"   stop-color="rgba(0,0,0,.55)"/>
    <stop offset="100%" stop-color="rgba(0,0,0,0)"/>
  </radialGradient>
  <!-- Sweat -->
  <radialGradient id="swt" cx="35%" cy="25%" r="70%">
    <stop offset="0%"  stop-color="#b8e0f8"/>
    <stop offset="100%" stop-color="#1e6898"/>
  </radialGradient>
</defs>

<!-- ══ GROUND SHADOW ══ -->
<ellipse id="gf-ground-shadow" cx="80" cy="374" rx="52" ry="7" fill="url(#gshadow)" opacity=".8"/>

<!-- ══ SHOES ══ (drawn first, behind legs) -->
<!-- Left shoe — anatomy: heel, mid, toe, sole stripe -->
<g id="gf-shoe-left">
  <path d="M32,347 Q30,362 38,366 L78,366 Q86,362 84,347 Z" fill="#080808"/>
  <rect x="34" y="352" width="50" height="6" rx="2" fill="#e0e0e0" opacity=".85"/>
  <path d="M34,340 L82,340 Q86,340 84,347 L32,347 Q30,340 34,340 Z" fill="url(#shoe)"/>
  <path d="M32,348 Q32,340 40,340 L55,340 L55,347 L32,347 Z" fill="#0e0e0e"/>
  <rect x="44" y="341" width="36" height="5" rx="1.5" fill="#1e1e1e"/>
  <line x1="46" y1="342" x2="78" y2="342" stroke="#2a2a2a" stroke-width=".8"/>
  <line x1="45" y1="345" x2="79" y2="345" stroke="#2a2a2a" stroke-width=".6"/>
  <path d="M34,360 L82,360 Q84,362 82,365 L36,365 Q32,364 34,360 Z" fill="url(#lime)" opacity=".88"/>
</g>
<!-- Right shoe -->
<g id="gf-shoe-right">
  <path d="M78,347 Q76,362 84,366 L124,366 Q132,362 128,347 Z" fill="#080808"/>
  <rect x="80" y="352" width="50" height="6" rx="2" fill="#e0e0e0" opacity=".85"/>
  <path d="M80,340 L128,340 Q132,340 128,347 L78,347 Q76,340 80,340 Z" fill="url(#shoe)"/>
  <path d="M78,348 Q78,340 86,340 L102,340 L102,347 L78,347 Z" fill="#0e0e0e"/>
  <rect x="92" y="341" width="34" height="5" rx="1.5" fill="#1e1e1e"/>
  <line x1="94" y1="342" x2="124" y2="342" stroke="#2a2a2a" stroke-width=".8"/>
  <line x1="93" y1="345" x2="125" y2="345" stroke="#2a2a2a" stroke-width=".6"/>
  <path d="M80,360 L126,360 Q128,362 126,365 L82,365 Q78,364 80,360 Z" fill="url(#lime)" opacity=".88"/>
</g>

<!-- ══ CALVES (attached to shoes, continuous with thighs) ══ -->
<g id="gf-leg-left">
  <!-- Calf + shin as one continuous connected shape -->
  <path d="M38,248 Q30,268 30,302 Q30,328 34,340 L74,340 Q78,328 78,302 Q78,268 70,248 Z" fill="url(#cloth)"/>
  <!-- Calf muscle belly (medial + lateral) -->
  <path d="M40,255 Q35,275 36,305" stroke="#202020" stroke-width="9" fill="none" stroke-linecap="round"/>
  <path d="M62,257 Q68,277 66,306" stroke="#141414" stroke-width="6" fill="none" stroke-linecap="round"/>
  <!-- Shin bone ridge -->
  <path d="M55,258 Q53,295 53,335" stroke="#111" stroke-width="2" fill="none" opacity=".6"/>
</g>
<g id="gf-leg-right">
  <path d="M88,248 Q80,268 80,302 Q80,328 84,340 L124,340 Q128,328 128,302 Q128,268 120,248 Z" fill="url(#cloth)"/>
  <path d="M90,255 Q85,275 86,305" stroke="#202020" stroke-width="9" fill="none" stroke-linecap="round"/>
  <path d="M112,257 Q118,277 116,306" stroke="#141414" stroke-width="6" fill="none" stroke-linecap="round"/>
  <path d="M105,258 Q103,295 103,335" stroke="#111" stroke-width="2" fill="none" opacity=".6"/>
</g>

<!-- ══ KNEES ══ -->
<ellipse cx="55" cy="248" rx="17" ry="11" fill="#141414"/>
<ellipse cx="55" cy="247" rx="11" ry="7"  fill="#1c1c1c"/>
<ellipse cx="53" cy="245" rx="4"  ry="3"  fill="#222" opacity=".8"/>
<ellipse cx="105" cy="248" rx="17" ry="11" fill="#141414"/>
<ellipse cx="105" cy="247" rx="11" ry="7"  fill="#1c1c1c"/>
<ellipse cx="103" cy="245" rx="4"  ry="3"  fill="#222" opacity=".8"/>

<!-- ══ THIGHS / SHORTS ══ (continuous with torso waist) -->
<g id="gf-thighs">
  <!-- Left thigh — V-shape from narrow waist to wide knee -->
  <path d="M40,180 Q28,200 28,228 Q28,244 38,250 L72,250 Q82,244 82,228 Q82,200 70,180 Z" fill="url(#shorts)"/>
  <!-- Quad sweep lines -->
  <path d="M44,185 Q36,208 38,238" stroke="#141414" stroke-width="7" fill="none" stroke-linecap="round" opacity=".7"/>
  <path d="M62,186 Q68,210 66,238" stroke="#111" stroke-width="5" fill="none" stroke-linecap="round" opacity=".55"/>
  <!-- Shorts hem lime -->
  <path d="M30,180 Q55,174 80,180" stroke="url(#lime)" stroke-width="3" fill="none" opacity=".5" stroke-linecap="round"/>
  <!-- Right thigh -->
  <path d="M90,180 Q78,200 78,228 Q78,244 88,250 L122,250 Q132,244 132,228 Q132,200 122,180 Z" fill="url(#shorts)"/>
  <path d="M94,185 Q86,208 88,238" stroke="#141414" stroke-width="7" fill="none" stroke-linecap="round" opacity=".7"/>
  <path d="M112,186 Q118,210 116,238" stroke="#111" stroke-width="5" fill="none" stroke-linecap="round" opacity=".55"/>
  <path d="M80,180 Q105,174 130,180" stroke="url(#lime)" stroke-width="3" fill="none" opacity=".5" stroke-linecap="round"/>
  <!-- Crotch / inner thigh join -->
  <path d="M78,182 Q80,190 82,182" fill="#060606" opacity=".9"/>
</g>

<!-- ══ TORSO (continuous shape from shoulders to waist) ══ -->
<g id="gf-torso">
  <!-- Main body — trapezoid V-taper: wide at shoulders, narrow waist -->
  <path d="M22,118 Q16,138 18,160 Q20,175 30,182 L130,182 Q140,175 142,160 Q144,138 138,118 Q118,106 80,103 Q42,106 22,118 Z" fill="url(#cloth)"/>

  <!-- LEFT PEC — shaped bulge -->
  <path d="M26,118 Q48,107 74,114 Q78,134 68,146 Q54,153 32,143 Q20,133 26,118 Z" fill="#222" opacity=".85"/>
  <path d="M32,120 Q50,111 70,117" stroke="#2e2e2e" stroke-width="2.5" fill="none" opacity=".7"/>
  <!-- RIGHT PEC -->
  <path d="M134,118 Q112,107 86,114 Q82,134 92,146 Q106,153 128,143 Q140,133 134,118 Z" fill="#222" opacity=".85"/>
  <path d="M128,120 Q110,111 90,117" stroke="#2e2e2e" stroke-width="2.5" fill="none" opacity=".7"/>
  <!-- Sternum line -->
  <line x1="80" y1="108" x2="80" y2="152" stroke="#0a0a0a" stroke-width="2.5" opacity=".7"/>
  <!-- Pec lower boundary -->
  <path d="M26,143 Q80,156 134,143" stroke="#111" stroke-width="2" fill="none" opacity=".5"/>

  <!-- ABS -->
  <path d="M66,154 Q80,149 94,154 Q92,164 80,167 Q68,164 66,154 Z" fill="#181818" opacity=".75"/>
  <path d="M65,168 Q80,163 95,168 Q93,178 80,181 Q67,178 65,168 Z" fill="#141414" opacity=".7"/>
  <line x1="80" y1="152" x2="80" y2="182" stroke="#0a0a0a" stroke-width="2" opacity=".6"/>
  <path d="M68,152 Q80,148 92,152" stroke="#0e0e0e" stroke-width="1.5" fill="none" opacity=".55"/>
  <path d="M67,167 Q80,162 93,167" stroke="#0e0e0e" stroke-width="1.5" fill="none" opacity=".5"/>

  <!-- Tank top straps -->
  <rect x="64" y="103" width="14" height="52" rx="6" fill="#1c1c1c" opacity=".75"/>
  <rect x="82" y="103" width="14" height="52" rx="6" fill="#1c1c1c" opacity=".75"/>
  <!-- Logo -->
  <polygon points="77,112 83,112 80,120" fill="url(#lime)" opacity=".95"/>

  <!-- Waistband -->
  <rect x="28" y="176" width="104" height="12" rx="4" fill="#0e0e0e"/>
  <rect x="28" y="185" width="104" height="3"  rx="1.5" fill="url(#lime)" opacity=".35"/>

  <!-- TRAPS (visible above tank, smooth into neck) -->
  <path d="M54,110 Q80,100 106,110 Q96,116 80,114 Q64,116 54,110 Z" fill="#1c1c1c" opacity=".8"/>
</g>

<!-- ══ LEFT ARM ══ — complete connected arm, shoulder→elbow→wrist→hand -->
<g id="gf-arm-left" transform-origin="28 122">
  <!-- Deltoid — connects torso shoulder to upper arm -->
  <path d="M18,115 Q10,128 12,145 Q16,156 24,162 Q34,162 40,152 Q44,140 40,124 Q32,110 18,115 Z" fill="url(#bicL)"/>
  <!-- Deltoid highlight stripe -->
  <path d="M20,118 Q14,132 16,148" stroke="#d49060" stroke-width="3" fill="none" stroke-linecap="round" opacity=".35"/>

  <!-- UPPER ARM — flows from deltoid -->
  <g id="gf-upper-arm-left">
    <path d="M16,148 Q10,162 12,192 Q14,208 22,216 L44,216 Q52,208 54,192 Q56,168 50,148 Z" fill="url(#bicL)"/>
    <!-- Bicep peak ridge -->
    <path d="M26,154 Q20,172 21,198" stroke="#e09868" stroke-width="4" fill="none" stroke-linecap="round" opacity=".38"/>
    <!-- Sleeve covering top of upper arm -->
    <path d="M16,148 Q10,148 10,160 L50,160 Q50,148 44,148 Z" fill="#1e1e1e" opacity=".85"/>
  </g>

  <!-- FOREARM — flows from elbow -->
  <g id="gf-forearm-left" transform-origin="30 216">
    <path d="M16,214 Q10,228 12,258 Q14,276 22,284 L42,284 Q50,276 52,258 Q54,230 48,214 Z" fill="url(#sk-side)"/>
    <!-- Forearm muscle mass -->
    <path d="M20,220 Q15,240 16,264" stroke="#c88050" stroke-width="5" fill="none" stroke-linecap="round" opacity=".4"/>
    <!-- Veins -->
    <path d="M26,224 Q24,248 22,272" stroke="#8c4010" stroke-width="1.6" fill="none" opacity=".55"/>
    <path d="M32,227 Q30,251 28,275" stroke="#8c4010" stroke-width="1.2" fill="none" opacity=".45"/>
    <path d="M37,229 Q36,252 35,274" stroke="#8c4010" stroke-width="1"   fill="none" opacity=".35"/>
    <!-- Branching vein -->
    <path d="M26,268 Q24,276 22,282" stroke="#8c4010" stroke-width="1.4" fill="none" opacity=".45"/>
    <path d="M28,270 Q32,278 34,283" stroke="#8c4010" stroke-width="1"   fill="none" opacity=".35"/>
    <!-- Wristband lime -->
    <rect x="13" y="276" width="38" height="9" rx="4.5" fill="url(#lime)" opacity=".9"/>
    <rect x="15" y="277" width="34" height="3" rx="1.5" fill="#d8ff7c" opacity=".35"/>
    <!-- HAND — gripping bar -->
    <path d="M14,283 Q12,292 20,296 L46,296 Q54,292 50,283 Z" fill="url(#sk)" opacity=".95"/>
    <path d="M20,285 L20,294 M26,284 L26,295 M32,284 L32,295 M38,284 L38,295 M44,285 L44,294" stroke="#8c4010" stroke-width="1.2" opacity=".5"/>
  </g>
</g>

<!-- ══ RIGHT ARM ══ -->
<g id="gf-arm-right" transform-origin="132 122">
  <!-- Deltoid -->
  <path d="M142,115 Q150,128 148,145 Q144,156 136,162 Q126,162 120,152 Q116,140 120,124 Q128,110 142,115 Z" fill="url(#bicR)"/>
  <path d="M140,118 Q146,132 144,148" stroke="#d49060" stroke-width="3" fill="none" stroke-linecap="round" opacity=".35"/>

  <!-- Upper arm -->
  <g id="gf-upper-arm-right">
    <path d="M144,148 Q150,162 148,192 Q146,208 138,216 L116,216 Q108,208 106,192 Q104,168 110,148 Z" fill="url(#bicR)"/>
    <path d="M134,154 Q140,172 139,198" stroke="#e09868" stroke-width="4" fill="none" stroke-linecap="round" opacity=".38"/>
    <path d="M144,148 Q150,148 150,160 L110,160 Q110,148 116,148 Z" fill="#1e1e1e" opacity=".85"/>
  </g>

  <!-- Forearm -->
  <g id="gf-forearm-right" transform-origin="130 216">
    <path d="M144,214 Q150,228 148,258 Q146,276 138,284 L118,284 Q110,276 108,258 Q106,230 112,214 Z" fill="url(#sk-side)"/>
    <path d="M140,220 Q145,240 144,264" stroke="#c88050" stroke-width="5" fill="none" stroke-linecap="round" opacity=".4"/>
    <path d="M134,224 Q136,248 138,272" stroke="#8c4010" stroke-width="1.6" fill="none" opacity=".55"/>
    <path d="M128,227 Q130,251 132,275" stroke="#8c4010" stroke-width="1.2" fill="none" opacity=".45"/>
    <path d="M123,229 Q124,252 125,274" stroke="#8c4010" stroke-width="1"   fill="none" opacity=".35"/>
    <path d="M134,268 Q136,276 138,282" stroke="#8c4010" stroke-width="1.4" fill="none" opacity=".45"/>
    <path d="M132,270 Q128,278 126,283" stroke="#8c4010" stroke-width="1"   fill="none" opacity=".35"/>
    <rect x="109" y="276" width="38" height="9" rx="4.5" fill="url(#lime)" opacity=".9"/>
    <rect x="111" y="277" width="34" height="3" rx="1.5" fill="#d8ff7c" opacity=".35"/>
    <path d="M110,283 Q108,292 116,296 L142,296 Q150,292 146,283 Z" fill="url(#sk)" opacity=".95"/>
    <path d="M116,285 L116,294 M122,284 L122,295 M128,284 L128,295 M134,284 L134,295 M140,285 L140,294" stroke="#8c4010" stroke-width="1.2" opacity=".5"/>
  </g>
</g>

<!-- ══ BARBELL (AT REST — hanging at arms' length) ══ -->
<g id="gf-barbell" transform-origin="80 292">
  <!-- Left plate 45lb -->
  <g id="gf-plate-left">
    <rect x="0"  y="276" width="14" height="32" rx="4" fill="url(#plate)"/>
    <rect x="14" y="277" width="2.5" height="30" rx="1" fill="#ddd" opacity=".22"/>
    <circle cx="7"  cy="292" r="4" fill="#444" opacity=".75"/>
    <circle cx="7"  cy="292" r="2" fill="#555"/>
    <!-- 25lb inner -->
    <rect x="14" y="280" width="10" height="24" rx="3" fill="#999"/>
    <rect x="23" y="281" width="1.5" height="22" rx="1" fill="#eee" opacity=".18"/>
    <circle cx="19" cy="292" r="3" fill="#555" opacity=".65"/>
  </g>
  <!-- Bar -->
  <rect x="23" y="285" width="114" height="12" rx="6" fill="url(#metal)"/>
  <rect x="25" y="286" width="110" height="3.5" rx="1.5" fill="#fff" opacity=".2"/>
  <!-- Knurling left -->
  <line x1="36" y1="286" x2="36" y2="297" stroke="#aaa" stroke-width="1.2" opacity=".55"/>
  <line x1="40" y1="286" x2="40" y2="297" stroke="#aaa" stroke-width="1.2" opacity=".55"/>
  <line x1="44" y1="286" x2="44" y2="297" stroke="#aaa" stroke-width="1"   opacity=".45"/>
  <!-- Knurling right -->
  <line x1="116" y1="286" x2="116" y2="297" stroke="#aaa" stroke-width="1.2" opacity=".55"/>
  <line x1="120" y1="286" x2="120" y2="297" stroke="#aaa" stroke-width="1.2" opacity=".55"/>
  <line x1="124" y1="286" x2="124" y2="297" stroke="#aaa" stroke-width="1"   opacity=".45"/>
  <!-- Collars -->
  <rect x="21" y="282" width="5" height="18" rx="2.5" fill="#777"/>
  <rect x="134" y="282" width="5" height="18" rx="2.5" fill="#777"/>
  <!-- Right plate 45lb -->
  <g id="gf-plate-right">
    <rect x="136" y="276" width="14" height="32" rx="4" fill="url(#plate)"/>
    <rect x="136" y="277" width="2.5" height="30" rx="1" fill="#ddd" opacity=".22"/>
    <circle cx="143" cy="292" r="4" fill="#444" opacity=".75"/>
    <circle cx="143" cy="292" r="2" fill="#555"/>
    <rect x="126" y="280" width="10" height="24" rx="3" fill="#999"/>
    <rect x="126" y="281" width="1.5" height="22" rx="1" fill="#eee" opacity=".18"/>
    <circle cx="131" cy="292" r="3" fill="#555" opacity=".65"/>
  </g>
</g>

<!-- ══ NECK (skin, connects head to torso) ══ -->
<g id="gf-neck">
  <path d="M66,100 Q70,93 80,91 Q90,93 94,100 L92,118 Q88,113 80,112 Q72,113 68,118 Z" fill="url(#sk)"/>
  <path d="M68,100 Q70,108 68,118" stroke="#8c4010" stroke-width="1.8" fill="none" opacity=".45"/>
  <path d="M92,100 Q90,108 92,118" stroke="#8c4010" stroke-width="1.8" fill="none" opacity=".4"/>
  <path d="M66,100 L68,118 Q72,114 72,106 Z" fill="#7a3a14" opacity=".3"/>
</g>

<!-- ══ HEAD ══ — realistic proportions, proper skull shape -->
<g id="gf-head" transform-origin="80 72">
  <!-- SKULL base — slightly wider at cheeks, narrower at temples -->
  <path d="M52,78 Q50,58 56,46 Q64,32 80,30 Q96,32 104,46 Q110,58 108,78 Q106,96 98,106 Q90,114 80,116 Q70,114 62,106 Q54,96 52,78 Z" fill="url(#sk-face)"/>

  <!-- Temporal shadow -->
  <path d="M52,78 Q50,62 56,48" stroke="#7a3a14" stroke-width="8" fill="none" stroke-linecap="round" opacity=".5"/>
  <path d="M108,78 Q110,62 104,48" stroke="#7a3a14" stroke-width="8" fill="none" stroke-linecap="round" opacity=".45"/>

  <!-- EARS — realistic shell shape -->
  <path d="M52,76 Q46,78 44,84 Q44,92 50,96 Q54,98 56,94 Q56,82 54,76 Z" fill="url(#sk)"/>
  <path d="M48,80 Q46,86 48,92" stroke="#8c4010" stroke-width="1.3" fill="none" opacity=".5"/>
  <path d="M108,76 Q114,78 116,84 Q116,92 110,96 Q106,98 104,94 Q104,82 106,76 Z" fill="url(#sk)"/>
  <path d="M112,80 Q114,86 112,92" stroke="#8c4010" stroke-width="1.3" fill="none" opacity=".5"/>

  <!-- HAIR — natural short, faded sides -->
  <path d="M54,76 Q52,52 58,38 Q66,24 80,22 Q94,24 102,38 Q108,52 106,76 Q100,64 92,60 Q86,57 80,57 Q74,57 68,60 Q60,64 54,76 Z" fill="url(#hair)"/>
  <!-- Fade sides (barbered look) -->
  <path d="M54,76 Q52,60 56,46" stroke="#080808" stroke-width="9" fill="none" stroke-linecap="round" opacity=".95"/>
  <path d="M106,76 Q108,60 104,46" stroke="#080808" stroke-width="9" fill="none" stroke-linecap="round" opacity=".9"/>
  <!-- Hair texture -->
  <path d="M64,34 Q80,28 96,34" stroke="#161616" stroke-width="2" fill="none" opacity=".55"/>
  <path d="M62,42 Q80,36 98,42" stroke="#141414" stroke-width="1.5" fill="none" opacity=".45"/>

  <!-- HEADBAND (lime) -->
  <path d="M54,76 Q66,68 80,66 Q94,68 106,76" stroke="url(#lime)" stroke-width="6" fill="none" stroke-linecap="round" opacity=".95"/>
  <path d="M55,77 Q68,69 80,68 Q92,69 105,77" stroke="#0a0f00" stroke-width="1.5" fill="none" opacity=".4"/>

  <!-- ══ FACE ══ -->
  <!-- Brow ridge shadow -->
  <path d="M60,82 Q80,77 100,82" fill="#8a4820" opacity=".12"/>

  <!-- EYEBROWS — thick, defined -->
  <path id="gf-brow-left"  d="M60,84 Q68,79 76,82"  stroke="#0e0e0e" stroke-width="4"   fill="none" stroke-linecap="round"/>
  <path d="M61,85 Q69,80 75,83"  stroke="#1a1a1a" stroke-width="1.5" fill="none" opacity=".5" stroke-linecap="round"/>
  <path id="gf-brow-right" d="M84,82 Q92,79 100,84" stroke="#0e0e0e" stroke-width="4"   fill="none" stroke-linecap="round"/>
  <path d="M85,83 Q93,80 99,85"  stroke="#1a1a1a" stroke-width="1.5" fill="none" opacity=".5" stroke-linecap="round"/>

  <!-- Eye socket depth -->
  <ellipse cx="68" cy="91" rx="10" ry="8.5" fill="#7a3a10" opacity=".18"/>
  <ellipse cx="92" cy="91" rx="10" ry="8.5" fill="#7a3a10" opacity=".18"/>

  <!-- EYE WHITES — almond shaped -->
  <path d="M58,91 Q68,84 78,91 Q68,98 58,91 Z" fill="#efece8"/>
  <path d="M82,91 Q92,84 102,91 Q92,98 82,91 Z" fill="#efece8"/>

  <!-- IRIS — dark, realistic -->
  <circle cx="68" cy="91" r="5.5" fill="#180c00"/>
  <circle cx="92" cy="91" r="5.5" fill="#180c00"/>
  <circle cx="68" cy="91" r="4.5" fill="#2e1400"/>
  <circle cx="92" cy="91" r="4.5" fill="#2e1400"/>
  <!-- PUPILS -->
  <circle id="gf-pupil-left"  cx="68" cy="91" r="3" fill="#040404"/>
  <circle id="gf-pupil-right" cx="92" cy="91" r="3" fill="#040404"/>
  <!-- Eye glints -->
  <circle cx="70" cy="88.5" r="1.6" fill="white" opacity=".9"/>
  <circle cx="94" cy="88.5" r="1.6" fill="white" opacity=".9"/>
  <circle cx="66" cy="93"   r=".7"  fill="white" opacity=".4"/>
  <circle cx="90" cy="93"   r=".7"  fill="white" opacity=".4"/>

  <!-- Upper lash line -->
  <path d="M59,87 Q68,83 77,87" stroke="#1e0a00" stroke-width="1.4" fill="none" opacity=".75"/>
  <path d="M83,87 Q92,83 101,87" stroke="#1e0a00" stroke-width="1.4" fill="none" opacity=".75"/>
  <!-- Lower lash line -->
  <path d="M59,95 Q68,98 77,95"  stroke="#8a5028" stroke-width=".9" fill="none" opacity=".4"/>
  <path d="M83,95 Q92,98 101,95" stroke="#8a5028" stroke-width=".9" fill="none" opacity=".4"/>

  <!-- EYELIDS for blink -->
  <rect id="gf-eyelid-left"  x="59" y="86" width="18" height="0" rx="3" fill="url(#sk-face)"/>
  <rect id="gf-eyelid-right" x="83" y="86" width="18" height="0" rx="3" fill="url(#sk-face)"/>

  <!-- NOSE — bridge, tip, nostrils -->
  <path d="M78,94 Q76,100 74,106" stroke="#8a4820" stroke-width="1.3" fill="none" opacity=".4"/>
  <path d="M82,94 Q84,100 86,106" stroke="#8a4820" stroke-width="1.3" fill="none" opacity=".4"/>
  <!-- Nose tip -->
  <path d="M74,106 Q78,111 80,112 Q82,111 86,106 Q83,109 80,109 Q77,109 74,106 Z" fill="#8c4820" opacity=".55"/>
  <!-- Nostrils -->
  <ellipse cx="74" cy="107" rx="3"   ry="2"   fill="#6a3010" opacity=".65"/>
  <ellipse cx="86" cy="107" rx="3"   ry="2"   fill="#6a3010" opacity=".65"/>
  <!-- Nose bridge highlight -->
  <path d="M79,96 Q80,102 80,107" stroke="#d49060" stroke-width="1.2" fill="none" opacity=".28"/>

  <!-- Nasolabial folds -->
  <path d="M73,106 Q71,110 72,116" stroke="#8a4820" stroke-width=".9" fill="none" opacity=".3"/>
  <path d="M87,106 Q89,110 88,116" stroke="#8a4820" stroke-width=".9" fill="none" opacity=".3"/>

  <!-- Cheekbone highlight -->
  <ellipse cx="58"  cy="96" rx="7" ry="4" fill="#c88050" opacity=".18"/>
  <ellipse cx="102" cy="96" rx="7" ry="4" fill="#c88050" opacity=".18"/>

  <!-- MOUTH — confident grin -->
  <path id="gf-mouth" d="M68,116 Q80,124 92,116" stroke="#5a2010" stroke-width="2.5" fill="none" stroke-linecap="round"/>
  <!-- Upper lip detail -->
  <path d="M70,115 Q76,112 80,113 Q84,112 90,115" stroke="#7a3018" stroke-width="1.4" fill="none" opacity=".6"/>
  <!-- Teeth glimpse -->
  <path d="M71,117 Q80,122 89,117" fill="#e8e0d8" opacity=".5"/>
  <!-- Lower lip -->
  <path d="M72,119 Q80,123 88,119" fill="#8a3818" opacity=".2"/>
  <!-- Corner dimples -->
  <circle cx="67" cy="117" r="2" fill="#8a4020" opacity=".22"/>
  <circle cx="93" cy="117" r="2" fill="#8a4020" opacity=".22"/>
  <!-- Chin shadow -->
  <path d="M70,122 Q80,128 90,122" fill="#7a3814" opacity=".2"/>
</g>

<!-- ══ SWEAT ══ -->
<g id="gf-sweat-container"></g>
</svg>`;
  }
  function createContainer() {
    const wrap = document.createElement('div');
    wrap.id = 'gf-athlete-wrap';
    wrap.setAttribute('aria-hidden', 'true');
    wrap.innerHTML = buildAthleteSVG();
    document.body.appendChild(wrap);
    return wrap;
  }

  function createCounterBadge() {
    const badge = document.createElement('div');
    badge.id = 'gf-curl-counter';
    badge.textContent = '0';
    document.body.appendChild(badge);
    return badge;
  }

  // ═══════════════════════════════════════════════════════════
  //  ANIMATIONS
  // ═══════════════════════════════════════════════════════════
  function initAnimations() {
    const gsap = window.gsap;
    if (!gsap) { console.warn('[GF Athlete] GSAP not loaded'); return; }
    state.gsapLoaded = true;

    const svg   = document.getElementById('gf-athlete-svg');
    const badge = document.getElementById('gf-curl-counter');

    const R = {
      head        : svg.querySelector('#gf-head'),
      neck        : svg.querySelector('#gf-neck'),
      torso       : svg.querySelector('#gf-torso'),
      thighs      : svg.querySelector('#gf-thighs'),
      armL        : svg.querySelector('#gf-arm-left'),
      armR        : svg.querySelector('#gf-arm-right'),
      forearmL    : svg.querySelector('#gf-forearm-left'),
      forearmR    : svg.querySelector('#gf-forearm-right'),
      barbell     : svg.querySelector('#gf-barbell'),
      plateL      : svg.querySelector('#gf-plate-left'),
      plateR      : svg.querySelector('#gf-plate-right'),
      eyelidL     : svg.querySelector('#gf-eyelid-left'),
      eyelidR     : svg.querySelector('#gf-eyelid-right'),
      browL       : svg.querySelector('#gf-brow-left'),
      browR       : svg.querySelector('#gf-brow-right'),
      mouth       : svg.querySelector('#gf-mouth'),
      shadow      : svg.querySelector('#gf-ground-shadow'),
      wrap        : document.getElementById('gf-athlete-wrap'),
      sweatCont   : svg.querySelector('#gf-sweat-container'),
    };

    // ── IDLE BREATHING ──────────────────────────────────────
    const breathTl = gsap.timeline({ repeat:-1, yoyo:true });
    breathTl
      .to(R.torso, { y:-3, scaleY:1.014, duration:2.2, ease:'sine.inOut', transformOrigin:'50% 100%' })
      .to(R.head,  { y:-2.5, rotation:1.8, duration:2.2, ease:'sine.inOut', transformOrigin:'50% 100%' }, 0)
      .to(R.neck,  { y:-1.5, duration:2.2, ease:'sine.inOut' }, 0)
      .to(R.armL,  { rotation:-4, duration:2.2, ease:'sine.inOut', transformOrigin:'50% 0%' }, 0)
      .to(R.armR,  { rotation: 4, duration:2.2, ease:'sine.inOut', transformOrigin:'50% 0%' }, 0)
      .to(R.shadow,{ scaleX:0.9, opacity:0.55, duration:2.2, ease:'sine.inOut', transformOrigin:'50% 50%' }, 0);

    // ── BODY SWAY ────────────────────────────────────────────
    gsap.to(R.wrap, { x:5, duration:4.2, repeat:-1, yoyo:true, ease:'sine.inOut' });

    // ── BLINK ────────────────────────────────────────────────
    function scheduleBlink() {
      const delay = 2.5 + Math.random() * 4.5;
      gsap.delayedCall(delay, () => {
        gsap.to([R.eyelidL, R.eyelidR], { height:15, duration:0.06, ease:'power2.in' });
        gsap.to([R.eyelidL, R.eyelidR], { height:0,  duration:0.09, ease:'power2.out', delay:0.07, onComplete:scheduleBlink });
      });
    }
    scheduleBlink();

    // ── SWEAT PARTICLES ──────────────────────────────────────
    function spawnSweat() {
      const n = 5 + Math.floor(Math.random() * 5);
      for (let i = 0; i < n; i++) {
        const p = document.createElementNS('http://www.w3.org/2000/svg','ellipse');
        p.setAttribute('rx', (1 + Math.random() * 2).toFixed(1));
        p.setAttribute('ry', (1.5 + Math.random() * 2.5).toFixed(1));
        p.setAttribute('cx', (55 + Math.random() * 50).toFixed(0));
        p.setAttribute('cy', (60 + Math.random() * 80).toFixed(0));
        p.setAttribute('fill', 'url(#swt)');
        R.sweatCont.appendChild(p);
        gsap.fromTo(p,
          { opacity:0.9, x:0, y:0 },
          { opacity:0, x:(Math.random()-.5)*24, y:-28-Math.random()*28,
            duration:0.7+Math.random()*.45, delay:Math.random()*.2,
            ease:'power1.out', onComplete:()=>p.remove() }
        );
      }
    }

    // ── +1 REP LABEL ─────────────────────────────────────────
    function showRepLabel() {
      const lbl = document.createElement('div');
      lbl.className = 'gf-rep-label';
      lbl.textContent = '+1 Rep 💪';
      const rect = R.wrap.getBoundingClientRect();
      lbl.style.bottom = (window.innerHeight - rect.top + 28) + 'px';
      document.body.appendChild(lbl);
      gsap.fromTo(lbl,
        { opacity:0, y:0 },
        { opacity:1, y:-10, duration:0.25, ease:'power2.out',
          onComplete:()=> gsap.to(lbl, { opacity:0, y:-50, duration:0.55, delay:0.6, ease:'power1.in', onComplete:()=>lbl.remove() }) }
      );
    }

    // ── MILESTONE TOAST ──────────────────────────────────────
    function showMilestone(msg) {
      const toast = document.createElement('div');
      toast.className = 'gf-milestone-toast';
      toast.textContent = msg;
      document.body.appendChild(toast);
      gsap.to(toast, {
        opacity:1, y:0, scale:1, duration:0.4, ease:'back.out(1.6)',
        onComplete:()=> gsap.to(toast, { opacity:0, y:-12, duration:0.4, delay:2.2, ease:'power1.in', onComplete:()=>toast.remove() })
      });
    }

    // ── COUNTER BADGE UPDATE ──────────────────────────────────
    function updateBadge(n) {
      badge.textContent = n;
      badge.style.opacity = '1';
      gsap.fromTo(badge, { scale:1.4 }, { scale:1, duration:0.35, ease:'elastic.out(1,0.5)' });
    }

    // ── CAMERA SHAKE ─────────────────────────────────────────
    function cameraShake() {
      document.body.classList.remove('gf-shake');
      void document.body.offsetWidth; // reflow
      document.body.classList.add('gf-shake');
      setTimeout(() => document.body.classList.remove('gf-shake'), 320);
    }

    // ── BARBELL CURL ANIMATION ───────────────────────────────
    function performCurl() {
      const upDur    = CURL_DURATION * 0.43;
      const holdSt   = upDur;
      const downSt   = holdSt + HOLD_DURATION;
      const downDur  = CURL_DURATION - downSt;

      const tl = gsap.timeline({
        onComplete: () => {
          state.isAnimating = false;
          if (state.queue > 0) {
            state.queue--;
            state.isAnimating = true;
            performCurl();
          }
        }
      });

      // Phase 1: CURL UP
      // Forearms rotate up — pivot at top of forearm group (elbow ~y216)
      tl.to(R.forearmL, { rotation:-108, duration:upDur, ease:'power2.inOut', transformOrigin:'50% 0%' }, 0);
      tl.to(R.forearmR, { rotation: 108, duration:upDur, ease:'power2.inOut', transformOrigin:'50% 0%' }, 0);
      // Upper arms angle forward slightly
      tl.to(R.armL, { rotation:14, duration:upDur, ease:'power1.inOut', transformOrigin:'50% 0%' }, 0);
      tl.to(R.armR, { rotation:-14, duration:upDur, ease:'power1.inOut', transformOrigin:'50% 0%' }, 0);
      // Barbell rises to chest — 160 viewBox, bar rests at y≈292, rises ~150px
      tl.to(R.barbell, { y:-152, duration:upDur, ease:'power2.inOut', transformOrigin:'50% 50%' }, 0);
      // Effort face
      tl.to([R.browL, R.browR], { y:-3.5, duration:upDur*.55, ease:'power1.in' }, 0);
      tl.to(R.mouth, { attr:{ d:'M70,116 Q80,112 90,116' }, duration:upDur*.5, ease:'power1.in' }, 0);
      // Torso lean back
      tl.to(R.torso, { rotation:-4, duration:upDur, ease:'power1.inOut', transformOrigin:'50% 100%' }, 0);
      tl.to([R.head, R.neck], { rotation:-5, y:-4, duration:upDur, ease:'power1.inOut', transformOrigin:'50% 100%' }, 0);
      tl.to(R.shadow, { scaleX:.8, opacity:.4, duration:upDur, ease:'sine.inOut', transformOrigin:'50% 50%' }, 0);

      // Phase 2: HOLD — plate shimmer
      tl.to([R.plateL, R.plateR], {
        scaleX:1.07, duration:HOLD_DURATION/2, yoyo:true, repeat:1,
        ease:'power2.inOut', transformOrigin:'50% 50%'
      }, holdSt);

      // Phase 3: LOWER DOWN
      tl.to(R.forearmL, { rotation:0, duration:downDur, ease:'power2.inOut', transformOrigin:'50% 0%' }, downSt);
      tl.to(R.forearmR, { rotation:0, duration:downDur, ease:'power2.inOut', transformOrigin:'50% 0%' }, downSt);
      tl.to(R.armL,     { rotation:0, duration:downDur, ease:'power1.inOut', transformOrigin:'50% 0%' }, downSt);
      tl.to(R.armR,     { rotation:0, duration:downDur, ease:'power1.inOut', transformOrigin:'50% 0%' }, downSt);
      tl.to(R.barbell,  { y:0, duration:downDur, ease:'power2.inOut', transformOrigin:'50% 50%' }, downSt);
      tl.to([R.browL, R.browR], { y:0, duration:downDur, ease:'power1.out' }, downSt);
      tl.to(R.mouth, { attr:{ d:'M68,116 Q80,124 92,116' }, duration:downDur*.6, ease:'power1.out' }, downSt);
      tl.to(R.torso,    { rotation:0, duration:downDur, ease:'power1.inOut', transformOrigin:'50% 100%' }, downSt);
      tl.to([R.head, R.neck], { rotation:0, y:0, duration:downDur, ease:'power1.inOut', transformOrigin:'50% 100%' }, downSt);
      tl.to(R.shadow,   { scaleX:1, opacity:.75, duration:downDur, ease:'sine.inOut', transformOrigin:'50% 50%' }, downSt);

      // Bonus effects (fire at hold start)
      tl.call(() => {
        state.curlCount++;
        playClinkSound();
        spawnSweat();
        cameraShake();
        showRepLabel();
        updateBadge(state.curlCount);
        if (state.curlCount === 10)  showMilestone('🔥 Keep Going!');
        if (state.curlCount === 25)  showMilestone('🏆 Consistency Builds Champions');
        if (state.curlCount > 25 && state.curlCount % 25 === 0) showMilestone('🏆 Unstoppable!');
      }, null, holdSt);

      return tl;
    }

    // ── PUBLIC TRIGGER ───────────────────────────────────────
    window.gfTriggerCurl = function () {
      if (state.tabHidden) return;
      if (state.isAnimating) {
        if (state.queue < 3) state.queue++;
        return;
      }
      state.isAnimating = true;
      performCurl();
    };

    // ── TAB VISIBILITY ───────────────────────────────────────
    document.addEventListener('visibilitychange', () => {
      state.tabHidden = document.hidden;
      document.hidden ? gsap.globalTimeline.pause() : gsap.globalTimeline.resume();
    });
  }

  // ═══════════════════════════════════════════════════════════
  //  EVENT LISTENERS
  // ═══════════════════════════════════════════════════════════
  function attachEventListeners() {
    // Click anywhere
    document.addEventListener('click', (e) => {
      const tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      window.gfTriggerCurl && window.gfTriggerCurl();
    });

    // CTA buttons (extra guarantee for programmatic triggers)
    document.querySelectorAll('.btn, .plan-book-btn, .msn-btn').forEach(btn => {
      btn.addEventListener('click', () => window.gfTriggerCurl && window.gfTriggerCurl());
    });

    // Scroll trigger intentionally removed — curl fires on click only
  }

  // ═══════════════════════════════════════════════════════════
  //  GSAP LAZY LOAD + BOOT
  // ═══════════════════════════════════════════════════════════
  function loadGSAP(cb) {
    if (window.gsap) { cb(); return; }
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js';
    s.async = true;
    s.onload  = cb;
    s.onerror = () => console.warn('[GF Athlete] GSAP load failed');
    document.head.appendChild(s);
  }

  function injectStyles() {
    if (document.getElementById('gf-athlete-styles')) return;
    const s = document.createElement('style');
    s.id = 'gf-athlete-styles';
    s.textContent = `
      #gf-athlete-wrap {
        position: fixed;
        bottom: 0;
        right: 20px;
        width: 210px;
        height: 475px;
        z-index: 8888;
        pointer-events: none;
        transform-origin: bottom center;
        will-change: transform;
      }
      #gf-athlete-svg { width:100%; height:100%; display:block; }

      @media (max-width: 900px) {
        #gf-athlete-wrap {
          right: 50%;
          transform: translateX(50%);
          transform-origin: bottom center;
          bottom: 62px;
          width: 190px;
        }
      }
      @media (max-width: 480px) {
        #gf-athlete-wrap { width: 165px; }
      }

      .gf-milestone-toast {
        position: fixed;
        bottom: 492px;
        right: 24px;
        z-index: 9000;
        background: linear-gradient(135deg,#C1FF6B,#9acd32);
        color: #0a0f00;
        font-family: 'Inter',sans-serif;
        font-weight: 900;
        font-size: .92rem;
        padding: 12px 22px;
        border-radius: 50px;
        box-shadow: 0 8px 32px rgba(193,255,107,.5);
        pointer-events: none;
        white-space: nowrap;
        opacity: 0;
        transform: translateY(18px) scale(0.88);
        letter-spacing: -.02em;
      }
      @media (max-width: 900px) {
        .gf-milestone-toast {
          right: 50%;
          transform: translateX(50%) translateY(18px) scale(0.88);
          bottom: 540px;
        }
      }

      .gf-rep-label {
        position: fixed;
        right: 64px;
        z-index: 9001;
        font-family: 'Inter',sans-serif;
        font-weight: 900;
        font-size: 1.1rem;
        color: #C1FF6B;
        text-shadow: 0 2px 14px rgba(193,255,107,.7);
        pointer-events: none;
        opacity: 0;
        letter-spacing: -.01em;
      }
      @media (max-width: 900px) {
        .gf-rep-label { right: 50%; transform: translateX(50%); }
      }

      @keyframes gf-shake {
        0%,100% { transform: translate(0,0) rotate(0); }
        20%      { transform: translate(-3px,1px) rotate(-.4deg); }
        40%      { transform: translate(3px,-2px) rotate(.4deg); }
        60%      { transform: translate(-2px,3px) rotate(-.2deg); }
        80%      { transform: translate(2px,-2px) rotate(.2deg); }
      }
      body.gf-shake { animation: gf-shake 0.28s ease-out; }

      #gf-curl-counter {
        position: fixed;
        bottom: 476px;
        right: 22px;
        z-index: 8999;
        width: 42px; height: 42px;
        background: rgba(8,12,0,.88);
        border: 2.5px solid #C1FF6B;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: 'Inter',sans-serif;
        font-weight: 900;
        font-size: .78rem;
        color: #C1FF6B;
        pointer-events: none;
        opacity: 0;
        transition: opacity .3s;
        box-shadow: 0 4px 18px rgba(193,255,107,.25);
      }
      @media (max-width: 900px) {
        #gf-curl-counter { right: calc(50% - 88px); bottom: 550px; }
      }
    `;
    document.head.appendChild(s);
  }

  function boot() {
    injectStyles();
    createContainer();
    createCounterBadge();
    loadGSAP(() => {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        initAnimations();
        attachEventListeners();
      }));
    });
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', boot)
    : boot();

})();
