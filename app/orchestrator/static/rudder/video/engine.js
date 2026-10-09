/* Motion-graphics engine for the AI Rudder / CALL-E interview explainer.
   Pure function of time: renderAt(seconds) draws one 1920x1080 frame.
   Used by player.html (live preview) and build.mjs (frame-by-frame MP4 render). */
(function () {
const W = 1920, H = 1080;
const C = {
  bg0: '#050f17', bg1: '#0a2230', teal: '#2ee6c5', teal2: '#14b8a6', blue: '#5aa9ff', orange: '#ffa94d',
  red: '#ff6b6b', green: '#4ade80', purple: '#b197fc', yellow: '#ffd43b', pink: '#f783ac',
  text: '#eaf4f7', muted: '#8fa9b6', dim: '#4d6573', card: 'rgba(11,30,42,0.92)'
};
const FONT = '-apple-system, "SF Pro Display", "Helvetica Neue", Arial, sans-serif';
const MONO = '"SF Mono", Menlo, Consolas, monospace';
let ctx;

/* ---------- math ---------- */
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const eo = x => 1 - Math.pow(1 - clamp(x), 3);
const eio = x => { x = clamp(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; };
const back = x => { x = clamp(x); const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
const P = (t, s, d = 0.6) => clamp((t - s) / d);
const lerp = (a, b, k) => a + (b - a) * k;
function rgba(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; }
function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

/* ---------- drawing primitives ---------- */
function font(size, w = 600, mono = false) { return `${w} ${size}px ${mono ? MONO : FONT}`; }
function T(s, x, y, o = {}) {
  ctx.save(); ctx.globalAlpha *= (o.a ?? 1);
  ctx.font = font(o.size || 32, o.w || 600, o.mono); ctx.fillStyle = o.c || C.text;
  ctx.textAlign = o.align || 'left'; ctx.textBaseline = o.base || 'middle';
  if (o.ls) ctx.letterSpacing = o.ls + 'px';
  if (o.glow) { ctx.shadowColor = o.glow; ctx.shadowBlur = o.blur || 24; }
  ctx.fillText(s, x, y); ctx.restore();
}
function MW(s, size, w = 600, mono = false, ls = 0) { ctx.save(); ctx.font = font(size, w, mono); if (ls) ctx.letterSpacing = ls + 'px'; const m = ctx.measureText(s).width; ctx.restore(); return m; }
function wrap(s, maxW, size, w = 500, mono = false) {
  const words = s.split(' '), out = []; let cur = '';
  for (const wd of words) { const tryS = cur ? cur + ' ' + wd : wd; if (MW(tryS, size, w, mono) > maxW && cur) { out.push(cur); cur = wd; } else cur = tryS; }
  if (cur) out.push(cur); return out;
}
function TW(s, x, y, maxW, o = {}) { // wrapped text, returns height used
  const size = o.size || 26, lh = o.lh || size * 1.32; const lines = wrap(s, maxW, size, o.w || 500, o.mono);
  lines.forEach((l, i) => T(l, x, y + i * lh, { ...o, base: 'top' })); return lines.length * lh;
}
function box(x, y, w, h, o = {}) {
  ctx.save(); ctx.globalAlpha *= (o.a ?? 1); ctx.beginPath(); ctx.roundRect(x, y, w, h, o.r ?? 18);
  if (o.fill !== null) { ctx.fillStyle = o.fill || C.card; if (o.glow) { ctx.shadowColor = o.glow; ctx.shadowBlur = o.blur || 34; } ctx.fill(); ctx.shadowBlur = 0; }
  if (o.stroke) { ctx.strokeStyle = o.stroke; ctx.lineWidth = o.lw || 2; if (o.dash) ctx.setLineDash(o.dash); ctx.stroke(); }
  ctx.restore();
}
function pop(cx, cy, p, fn, o = {}) {
  if (p <= 0) return; ctx.save(); ctx.globalAlpha *= clamp(p * 1.5);
  const s = o.noscale ? 1 : lerp(o.from ?? 0.7, 1, back(p));
  ctx.translate(cx + (1 - eo(p)) * (o.dx || 0), cy + (1 - eo(p)) * (o.dy ?? 26)); ctx.scale(s, s); ctx.translate(-cx, -cy);
  fn(); ctx.restore();
}
function card(x, y, w, h, col, p, inner, o = {}) {
  pop(x + w / 2, y + h / 2, p, () => {
    box(x, y, w, h, { fill: o.fill || C.card, stroke: rgba(col, o.hot ? 0.95 : 0.5), lw: o.hot ? 3 : 2, glow: o.hot ? rgba(col, 0.55) : null, blur: 44, r: o.r ?? 20 });
    if (!o.nobar) box(x + 14, y + 18, 5, h - 36, { fill: col, r: 3 });
    inner && inner();
  }, o);
}
function chip(cx, cy, label, col, p, o = {}) {
  const size = o.size || 24, pad = o.pad || 20, w = MW(label, size, o.w || 600, o.mono) + pad * 2 + (o.icon ? size + 8 : 0), h = size + 22;
  if (p > 0) pop(cx, cy, p, () => {
    box(cx - w / 2, cy - h / 2, w, h, { fill: o.fill || rgba(col, 0.14), stroke: rgba(col, o.on ? 1 : 0.7), lw: o.on ? 3 : 2, r: h / 2, glow: o.on ? rgba(col, 0.6) : null });
    let tx = cx - w / 2 + pad;
    if (o.icon) { icon(o.icon, tx + size / 2, cy, size, col, 2.5); tx += size + 8; }
    T(label, tx, cy + 1, { size, c: o.tc || C.text, w: o.w || 600, mono: o.mono });
  }, { from: 0.5, dy: 14 });
  return w;
}
function chipRow(labels, cx, cy, gap, col, pf, o = {}) {
  const ws = labels.map(l => MW(typeof l === 'string' ? l : l.t, o.size || 24, o.w || 600, o.mono) + (o.pad || 20) * 2 + ((l.icon) ? (o.size || 24) + 8 : 0));
  const total = ws.reduce((a, b) => a + b, 0) + gap * (labels.length - 1); let x = cx - total / 2;
  labels.forEach((l, i) => { const lab = typeof l === 'string' ? l : l.t; const c = (typeof l === 'object' && l.c) || (typeof col === 'function' ? col(i) : col);
    chip(x + ws[i] / 2, cy, lab, c, pf(i), { ...o, icon: l.icon, on: l.on }); x += ws[i] + gap; });
}
function qpt(x1, y1, cx, cy, x2, y2, u) { const a = (1 - u) * (1 - u), b = 2 * (1 - u) * u, c = u * u; return [a * x1 + b * cx + c * x2, a * y1 + b * cy + c * y2]; }
function curve(x1, y1, cx, cy, x2, y2, p, col, o = {}) {
  if (p <= 0) return; const k = eio(p), N = 60;
  ctx.save(); ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = o.lw || 3; ctx.globalAlpha *= o.a ?? 1; ctx.lineCap = 'round';
  if (o.glow) { ctx.shadowColor = col; ctx.shadowBlur = 16; }
  if (o.dash) { ctx.setLineDash(o.dash); ctx.lineDashOffset = -(o.flow || 0) * 60; }
  ctx.beginPath(); for (let i = 0; i <= N; i++) { const [x, y] = qpt(x1, y1, cx, cy, x2, y2, k * i / N); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); } ctx.stroke(); ctx.setLineDash([]);
  if (!o.nohead && k > 0.04) {
    const [xa, ya] = qpt(x1, y1, cx, cy, x2, y2, Math.max(0, k - 0.02)), [xe, ye] = qpt(x1, y1, cx, cy, x2, y2, k);
    const a = Math.atan2(ye - ya, xe - xa), hs = o.hs || 16;
    ctx.beginPath(); ctx.moveTo(xe, ye); ctx.lineTo(xe - hs * Math.cos(a - 0.45), ye - hs * Math.sin(a - 0.45)); ctx.lineTo(xe - hs * Math.cos(a + 0.45), ye - hs * Math.sin(a + 0.45)); ctx.closePath(); ctx.fill();
  }
  ctx.restore();
}
function arrow(x1, y1, x2, y2, p, col, o = {}) { curve(x1, y1, (x1 + x2) / 2, (y1 + y2) / 2, x2, y2, p, col, o); }
function packet(x1, y1, cx, cy, x2, y2, u, col, o = {}) {
  if (u < 0 || u > 1) return; ctx.save();
  for (let i = 5; i >= 0; i--) { const uu = u - i * 0.018; if (uu < 0) continue; const [x, y] = qpt(x1, y1, cx, cy, x2, y2, uu);
    ctx.globalAlpha = (1 - i / 6) * (o.a ?? 1); ctx.fillStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 22; ctx.beginPath(); ctx.arc(x, y, (o.r || 9) * (1 - i * 0.12), 0, Math.PI * 2); ctx.fill(); }
  ctx.restore();
  if (o.label) { const [x, y] = qpt(x1, y1, cx, cy, x2, y2, u); T(o.label, x, y - 26, { size: 20, c: col, align: 'center', mono: true, w: 600 }); }
}
function linePacket(x1, y1, x2, y2, u, col, o) { packet(x1, y1, (x1 + x2) / 2, (y1 + y2) / 2, x2, y2, u, col, o); }
function badge(cx, cy, n, col, on, p = 1) {
  pop(cx, cy, p, () => {
    ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, 24, 0, Math.PI * 2); ctx.fillStyle = on ? col : '#0b1d28'; if (on) { ctx.shadowColor = col; ctx.shadowBlur = 30; }
    ctx.fill(); ctx.shadowBlur = 0; ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.stroke(); ctx.restore();
    T(String(n), cx, cy + 1, { size: 24, w: 800, c: on ? '#04131b' : col, align: 'center' });
  }, { from: 0.3 });
}
function ring(cx, cy, r, col, t, o = {}) { // pulsing ring
  for (let i = 0; i < (o.n || 3); i++) { const k = ((t * (o.speed || 0.5) + i / (o.n || 3)) % 1);
    ctx.save(); ctx.globalAlpha = (1 - k) * (o.a ?? 0.6); ctx.strokeStyle = col; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(cx, cy, r + k * (o.spread || 120), 0, Math.PI * 2); ctx.stroke(); ctx.restore(); }
}
function wave(cx, cy, w, h, n, t, col, amp = 1) {
  const bw = w / n; ctx.save(); ctx.fillStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 14;
  for (let i = 0; i < n; i++) { const x = cx - w / 2 + i * bw; const env = Math.sin(Math.PI * (i + 0.5) / n);
    const v = (0.35 + 0.65 * Math.abs(Math.sin(t * 5.1 + i * 0.55) * Math.cos(t * 2.3 + i * 0.21))) * env * amp; const bh = Math.max(4, v * h);
    ctx.beginPath(); ctx.roundRect(x + bw * 0.2, cy - bh / 2, bw * 0.6, bh, bw * 0.3); ctx.fill(); }
  ctx.restore();
}
function typed(s, p) { return s.slice(0, Math.floor(s.length * clamp(p))); }
function caret(t) { return (Math.floor(t * 2) % 2) ? '' : '▌'; }

/* ---------- icons (stroke style) ---------- */
function icon(name, cx, cy, s, col, lw = 3) {
  ctx.save(); ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = lw; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; const u = s / 2; const PI = Math.PI;
  ctx.beginPath();
  switch (name) {
    case 'db':
      ctx.ellipse(cx, cy - u * .7, u * .8, u * .28, 0, 0, PI * 2); ctx.stroke(); ctx.beginPath();
      ctx.moveTo(cx - u * .8, cy - u * .7); ctx.lineTo(cx - u * .8, cy + u * .7); ctx.ellipse(cx, cy + u * .7, u * .8, u * .28, 0, PI, 0, true); ctx.lineTo(cx + u * .8, cy - u * .7); ctx.stroke();
      ctx.beginPath(); ctx.ellipse(cx, cy, u * .8, u * .28, 0, 0, PI); ctx.stroke(); break;
    case 'phone':
      ctx.roundRect(cx - u * .5, cy - u * .9, u, u * 1.8, u * .18); ctx.stroke(); ctx.beginPath(); ctx.moveTo(cx - u * .15, cy + u * .65); ctx.lineTo(cx + u * .15, cy + u * .65); ctx.stroke(); break;
    case 'person':
      ctx.arc(cx, cy - u * .42, u * .34, 0, PI * 2); ctx.stroke(); ctx.beginPath(); ctx.arc(cx, cy + u * .85, u * .72, PI * 1.08, PI * 1.92); ctx.stroke(); break;
    case 'building':
      ctx.rect(cx - u * .65, cy - u * .85, u * 1.3, u * 1.7); ctx.stroke();
      for (let r = 0; r < 3; r++) for (let c = 0; c < 2; c++) { ctx.beginPath(); ctx.rect(cx - u * .4 + c * u * .5, cy - u * .6 + r * u * .45, u * .25, u * .22); ctx.stroke(); } break;
    case 'chat':
      ctx.roundRect(cx - u * .85, cy - u * .65, u * 1.7, u * 1.1, u * .3); ctx.stroke(); ctx.beginPath(); ctx.moveTo(cx - u * .35, cy + u * .45); ctx.lineTo(cx - u * .55, cy + u * .85); ctx.lineTo(cx + u * .05, cy + u * .45); ctx.stroke(); break;
    case 'shield':
      ctx.moveTo(cx, cy - u * .9); ctx.lineTo(cx + u * .75, cy - u * .55); ctx.quadraticCurveTo(cx + u * .7, cy + u * .55, cx, cy + u * .9); ctx.quadraticCurveTo(cx - u * .7, cy + u * .55, cx - u * .75, cy - u * .55); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx - u * .3, cy); ctx.lineTo(cx - u * .05, cy + u * .28); ctx.lineTo(cx + u * .35, cy - u * .25); ctx.stroke(); break;
    case 'check': ctx.moveTo(cx - u * .55, cy); ctx.lineTo(cx - u * .15, cy + u * .45); ctx.lineTo(cx + u * .6, cy - u * .45); ctx.stroke(); break;
    case 'cross': ctx.moveTo(cx - u * .45, cy - u * .45); ctx.lineTo(cx + u * .45, cy + u * .45); ctx.moveTo(cx + u * .45, cy - u * .45); ctx.lineTo(cx - u * .45, cy + u * .45); ctx.stroke(); break;
    case 'warn':
      ctx.moveTo(cx, cy - u * .8); ctx.lineTo(cx + u * .85, cy + u * .7); ctx.lineTo(cx - u * .85, cy + u * .7); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx, cy - u * .25); ctx.lineTo(cx, cy + u * .2); ctx.stroke(); ctx.beginPath(); ctx.arc(cx, cy + u * .45, lw * .6, 0, PI * 2); ctx.fill(); break;
    case 'gear':
      ctx.arc(cx, cy, u * .45, 0, PI * 2); ctx.stroke();
      for (let i = 0; i < 8; i++) { const a = i * PI / 4; ctx.beginPath(); ctx.moveTo(cx + Math.cos(a) * u * .6, cy + Math.sin(a) * u * .6); ctx.lineTo(cx + Math.cos(a) * u * .85, cy + Math.sin(a) * u * .85); ctx.stroke(); } break;
    case 'spark':
      ctx.moveTo(cx, cy - u * .9); ctx.quadraticCurveTo(cx, cy, cx + u * .9, cy); ctx.quadraticCurveTo(cx, cy, cx, cy + u * .9); ctx.quadraticCurveTo(cx, cy, cx - u * .9, cy); ctx.quadraticCurveTo(cx, cy, cx, cy - u * .9); ctx.stroke(); break;
    case 'bell':
      ctx.moveTo(cx - u * .6, cy + u * .45); ctx.quadraticCurveTo(cx - u * .55, cy - u * .75, cx, cy - u * .75); ctx.quadraticCurveTo(cx + u * .55, cy - u * .75, cx + u * .6, cy + u * .45); ctx.closePath(); ctx.stroke();
      ctx.beginPath(); ctx.arc(cx, cy + u * .62, u * .14, 0, PI * 2); ctx.stroke(); break;
    case 'cal':
      ctx.roundRect(cx - u * .8, cy - u * .65, u * 1.6, u * 1.45, u * .15); ctx.stroke(); ctx.beginPath(); ctx.moveTo(cx - u * .8, cy - u * .25); ctx.lineTo(cx + u * .8, cy - u * .25);
      ctx.moveTo(cx - u * .4, cy - u * .85); ctx.lineTo(cx - u * .4, cy - u * .5); ctx.moveTo(cx + u * .4, cy - u * .85); ctx.lineTo(cx + u * .4, cy - u * .5); ctx.stroke(); break;
    case 'mail':
      ctx.roundRect(cx - u * .85, cy - u * .55, u * 1.7, u * 1.1, u * .12); ctx.stroke(); ctx.beginPath(); ctx.moveTo(cx - u * .8, cy - u * .45); ctx.lineTo(cx, cy + u * .1); ctx.lineTo(cx + u * .8, cy - u * .45); ctx.stroke(); break;
    case 'lock':
      ctx.roundRect(cx - u * .6, cy - u * .1, u * 1.2, u * .95, u * .12); ctx.stroke(); ctx.beginPath(); ctx.arc(cx, cy - u * .15, u * .38, PI, 0); ctx.stroke(); break;
    case 'clock':
      ctx.arc(cx, cy, u * .8, 0, PI * 2); ctx.stroke(); ctx.beginPath(); ctx.moveTo(cx, cy - u * .5); ctx.lineTo(cx, cy); ctx.lineTo(cx + u * .35, cy + u * .2); ctx.stroke(); break;
    case 'q':
      ctx.arc(cx, cy, u * .85, 0, PI * 2); ctx.stroke(); T('?', cx, cy + 2, { size: s * .7, w: 800, c: col, align: 'center' }); break;
    case 'globe':
      ctx.arc(cx, cy, u * .85, 0, PI * 2); ctx.stroke(); ctx.beginPath(); ctx.ellipse(cx, cy, u * .38, u * .85, 0, 0, PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx - u * .85, cy); ctx.lineTo(cx + u * .85, cy); ctx.stroke(); break;
    case 'star':
      for (let i = 0; i < 10; i++) { const a = -PI / 2 + i * PI / 5, r = i % 2 ? u * .4 : u * .9; const x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); } ctx.closePath(); ctx.stroke(); break;
  }
  ctx.restore();
}
function iconCircle(name, cx, cy, r, col, o = {}) {
  ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fillStyle = rgba(col, o.fillA ?? 0.14); if (o.glow) { ctx.shadowColor = col; ctx.shadowBlur = 36; } ctx.fill(); ctx.shadowBlur = 0;
  ctx.strokeStyle = rgba(col, 0.9); ctx.lineWidth = 2.5; ctx.stroke(); ctx.restore(); icon(name, cx, cy, r * 1.05, col, o.lw || 3);
}

/* ---------- background ---------- */
const R = rng(42), PARTS = Array.from({ length: 78 }, () => ({ x: R() * W, y: R() * H, vx: (R() - .5) * 26, vy: (R() - .5) * 18, r: 1 + R() * 2.2 }));
function bg(T0) {
  const g = ctx.createLinearGradient(0, 0, W, H); g.addColorStop(0, C.bg0); g.addColorStop(1, C.bg1); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const blobs = [[C.teal, 0.10, 380, 300, 0.11], [C.blue, 0.09, 1500, 260, 0.08], [C.purple, 0.07, 1200, 860, 0.06]];
  for (const [c, a, bx, by, sp] of blobs) { const x = bx + Math.sin(T0 * sp * 2) * 180, y = by + Math.cos(T0 * sp * 1.6) * 110;
    const rg = ctx.createRadialGradient(x, y, 0, x, y, 620); rg.addColorStop(0, rgba(c, a)); rg.addColorStop(1, rgba(c, 0)); ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H); }
  ctx.save(); ctx.fillStyle = 'rgba(143,169,182,0.07)'; const off = (T0 * 8) % 48;
  for (let x = -48 + off; x < W; x += 48) for (let y = 24; y < H; y += 48) { ctx.fillRect(x, y, 2, 2); } ctx.restore();
  const pts = PARTS.map(p => [((p.x + p.vx * T0) % W + W) % W, ((p.y + p.vy * T0) % H + H) % H, p.r]);
  ctx.save(); ctx.lineWidth = 1;
  for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) { const dx = pts[i][0] - pts[j][0], dy = pts[i][1] - pts[j][1], d2 = dx * dx + dy * dy;
    if (d2 < 150 * 150) { ctx.strokeStyle = rgba(C.teal, 0.10 * (1 - Math.sqrt(d2) / 150)); ctx.beginPath(); ctx.moveTo(pts[i][0], pts[i][1]); ctx.lineTo(pts[j][0], pts[j][1]); ctx.stroke(); } }
  ctx.fillStyle = rgba(C.teal, 0.35); for (const [x, y, r] of pts) { ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); }
  ctx.restore();
  const v = ctx.createRadialGradient(W / 2, H / 2, H * 0.35, W / 2, H / 2, H * 0.95); v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.45)'); ctx.fillStyle = v; ctx.fillRect(0, 0, W, H);
}
function header(num, total, title, t, col = C.teal) {
  const p = eo(P(t, 0.1, 0.7));
  ctx.save(); ctx.globalAlpha = p;
  T(`CHAPTER ${String(num).padStart(2, '0')} / ${total}`, 96 - (1 - p) * 40, 74, { size: 20, mono: true, c: col, ls: 3, w: 700 });
  T(title, 96 - (1 - p) * 60, 120, { size: 46, w: 800 });
  box(96, 152, 140 * eo(P(t, 0.4, 0.8)), 5, { fill: col, r: 3, glow: col, blur: 18 });
  T('AI RUDDER · CALL-E · INTERVIEW PREP', W - 96, 74, { size: 16, mono: true, c: C.dim, align: 'right', ls: 2 });
  ctx.restore();
}

/* ---------- helpers bound per-scene ---------- */
function mkS(scene, t) {
  const at = i => i < scene.lines.length ? scene.lines[i].start : scene.dur;
  return { t, d: scene.dur, at, p: (i, off = 0, len = 0.7) => P(t, at(i) + off, len), on: i => t >= at(i) && t < at(i + 1), since: i => t - at(i) };
}

/* =====================================================================
   SCENES
   Each line: { t: caption text, s?: spoken override }
   ===================================================================== */
const SC = [];

/* 1 — Title */
SC.push({ title: 'Welcome', noHeader: true, lines: [
  { t: 'Welcome to your AI Rudder interview crash course.' },
  { t: "In the next few minutes you'll learn the company, its CALL-E product, the role, and the project you built." },
  { t: 'And for each one, exactly what to say.' },
], draw(t, S) {
  const cx = W / 2;
  ring(cx, 380, 120, C.teal, t, { n: 4, spread: 260, a: 0.35, speed: 0.35 });
  pop(cx, 380, P(t, 0.1, 0.9), () => { ctx.save(); ctx.beginPath(); ctx.arc(cx, 380, 120, 0, Math.PI * 2); ctx.fillStyle = 'rgba(8,28,38,0.95)'; ctx.shadowColor = C.teal; ctx.shadowBlur = 60; ctx.fill(); ctx.restore();
    wave(cx, 380, 190, 120, 15, t, C.teal, eo(P(t, 0.3, 1))); });
  const title = 'AI Rudder  ×  CALL-E'; const tw = MW(title, 110, 800); let x = cx - tw / 2;
  for (let i = 0; i < title.length; i++) { const ch = title[i], w = MW(ch, 110, 800), k = eo(P(t, 0.5 + i * 0.04, 0.5));
    T(ch, x, 590 + (1 - k) * 40, { size: 110, w: 800, a: k, c: ch === '×' ? C.orange : C.text, glow: ch === '×' ? C.orange : null }); x += w; }
  T('INTERVIEW CRASH COURSE', cx, 680, { size: 28, mono: true, c: C.teal, align: 'center', ls: 8, a: eo(P(t, 1.4, 0.8)) });
  chipRow([{ t: 'The company', icon: 'building' }, { t: 'CALL-E', icon: 'phone' }, { t: 'The role: CSM + FDE', icon: 'person' }, { t: 'Your project', icon: 'gear' },
    { t: 'What to say', icon: 'chat', c: C.orange, on: S.t > S.at(2) }], cx, 800, 22, C.teal, i => i < 4 ? S.p(1, 0.5 + i * 0.6) : S.p(2, 0.1), { size: 26 });
} });

/* 2 — Company */
SC.push({ title: 'AI Rudder at a glance', lines: [
  { t: 'AI Rudder is a Singapore-headquartered voice AI company, founded in 2019.' },
  { t: 'It helps enterprises automate high-volume customer conversations across voice, chat and omnichannel contact centers.' },
  { t: 'It supports more than 500 companies in 22 countries, and has delivered over 8 billion calls.', s: 'It supports more than five hundred companies, in twenty-two countries, and has delivered over eight billion calls.' },
  { t: 'Local teams serve customers across Southeast Asia, Latin America, China and the US.' },
], draw(t, S) {
  // facts
  const facts = [['building', 'HQ', 'Singapore'], ['clock', 'Founded', '2019'], ['star', 'Series B', 'US$50M · 2022']];
  facts.forEach(([ic, k, v], i) => card(96, 210 + i * 104, 600, 88, C.teal, S.p(0, 0.3 + i * 0.35), () => {
    iconCircle(ic, 160, 254 + i * 104, 26, C.teal); T(k, 210, 254 + i * 104, { size: 24, c: C.muted, w: 500 }); T(v, 680, 254 + i * 104, { size: 32, w: 700, align: 'right' }); }));
  chipRow([{ t: 'Voice', icon: 'phone' }, { t: 'Chat', icon: 'chat' }, { t: 'Omnichannel', icon: 'globe' }], 396, 560, 18, C.blue, i => S.p(1, 0.6 + i * 0.4), { size: 26 });
  const nums = [[500, '+', 'companies'], [22, '', 'countries'], [8, 'B+', 'calls delivered']];
  nums.forEach(([n, suf, lab], i) => { const p = S.p(2, i * 0.9, 1.6), x = 96 + i * 210;
    pop(x + 95, 720, P(t, S.at(2) + i * 0.9, 0.5), () => { box(x, 640, 190, 170, { fill: 'rgba(10,30,42,0.9)', stroke: rgba(C.orange, 0.6) });
      T(Math.round(n * eo(p)) + suf, x + 95, 712, { size: 62, w: 800, c: C.orange, align: 'center', glow: C.orange, blur: 18 }); T(lab, x + 95, 774, { size: 22, c: C.muted, align: 'center', w: 500 }); }); });
  // map
  const mx = lon => 860 + (lon + 130) / 265 * 940, my = lat => 230 + (45 - lat) / 62 * 600;
  ctx.save(); ctx.globalAlpha = eo(P(t, 0.2, 1));
  box(820, 190, 1010, 690, { fill: 'rgba(8,24,34,0.6)', stroke: 'rgba(143,169,182,0.18)' });
  for (let lon = -125; lon <= 135; lon += 6) for (let lat = 42; lat >= -14; lat -= 6) { ctx.fillStyle = 'rgba(46,230,197,0.10)'; ctx.beginPath(); ctx.arc(mx(lon), my(lat), 2, 0, Math.PI * 2); ctx.fill(); }
  T('Where AI Rudder works', 850, 222, { size: 20, mono: true, c: C.muted });
  ctx.restore();
  const sg = [mx(103.8), my(1.35)];
  const cities = [['Jakarta', 106.8, -6.2], ['Kuala Lumpur', 101.7, 3.1, 'l'], ['Bangkok', 100.5, 13.75, 'l'], ['Manila', 121, 14.6], ['Shanghai', 121.5, 31.2], ['Mexico City', -99.1, 19.4], ['United States', -98, 38]];
  cities.forEach(([name, lon, lat, side], i) => { const x = mx(lon), y = my(lat), p = S.p(3, i * 0.35, 1.1);
    const cy = Math.min(y, sg[1]) - (Math.abs(x - sg[0]) > 400 ? 300 : 60);
    curve(sg[0], sg[1], (sg[0] + x) / 2, cy, x, y, p, rgba(C.teal, 0.8), { lw: 2.5, nohead: true, glow: true });
    if (p > 0.95) { const u = ((t - S.at(3) - i * 0.35) * 0.45) % 1; packet(sg[0], sg[1], (sg[0] + x) / 2, cy, x, y, u, C.teal, { r: 6, a: 0.8 }); }
    pop(x, y, P(t, S.at(3) + i * 0.35 + 0.8, 0.5), () => { ctx.save(); ctx.fillStyle = C.teal; ctx.shadowColor = C.teal; ctx.shadowBlur = 20; ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      T(name, side === 'l' ? x - 16 : x + 16, y - 18, { size: 20, c: C.text, align: side === 'l' ? 'right' : 'left', w: 600 }); });
  });
  if (t > S.at(0)) { ring(sg[0], sg[1], 12, C.orange, t, { n: 3, spread: 70, a: 0.8, speed: 0.7 });
    pop(sg[0], sg[1], S.p(0, 0.2), () => { ctx.save(); ctx.fillStyle = C.orange; ctx.shadowColor = C.orange; ctx.shadowBlur = 30; ctx.beginPath(); ctx.arc(sg[0], sg[1], 12, 0, Math.PI * 2); ctx.fill(); ctx.restore();
      T('Singapore HQ', sg[0] - 22, sg[1] + 36, { size: 24, w: 800, c: C.orange, align: 'right' }); }); }
} });

/* 3 — Products */
SC.push({ title: 'What AI Rudder sells', lines: [
  { t: 'Its products include the AI Voice Agent, the AI Chat Agent, BotLab for building and monitoring agents, an omnichannel AI contact center, and CALL-E.' },
  { t: 'Typical use cases are collections and payment reminders, customer service, KYC and verification, telemarketing, and quality assurance.', s: 'Typical use cases are collections and payment reminders, customer service, K.Y.C. and verification, telemarketing, and quality assurance.' },
  { t: 'Key industries are banking and fintech, insurance, e-commerce, logistics and telecom.' },
], draw(t, S) {
  const hx = 960, hy = 420;
  ring(hx, hy, 100, C.teal, t, { n: 3, spread: 90, a: 0.4, speed: 0.4 });
  pop(hx, hy, P(t, 0.2, 0.8), () => { ctx.save(); ctx.beginPath(); ctx.arc(hx, hy, 100, 0, Math.PI * 2); ctx.fillStyle = '#0a2533'; ctx.shadowColor = C.teal; ctx.shadowBlur = 50; ctx.fill();
    ctx.setLineDash([10, 10]); ctx.lineDashOffset = -t * 30; ctx.strokeStyle = C.teal; ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(hx, hy, 116, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    T('AI Rudder', hx, hy - 12, { size: 34, w: 800, align: 'center' }); T('platform', hx, hy + 26, { size: 22, c: C.muted, align: 'center', mono: true }); });
  const prods = [['AI Voice Agent', 'Human-like inbound & outbound calls', 330, 300, C.teal, 'phone'], ['AI Chat Agent', 'WhatsApp, web & social chat', 330, 540, C.blue, 'chat'],
    ['BotLab', 'No-code build & monitor agents', 960, 660, C.purple, 'gear'],
    ['Omnichannel / AICC', 'Voice · SMS · email · social', 1590, 300, C.yellow, 'globe'], ['CALL-E', 'Goal-based phone agent (yours!)', 1590, 540, C.orange, 'spark']];
  prods.forEach(([n, d, x, y, col, ic], i) => { const p = S.p(0, 0.4 + i * 1.0, 0.8);
    const ex = x + (x < hx ? 230 : x > hx ? -230 : 0), ey = y + (x === hx ? -60 : 0), a0 = Math.atan2(ey - hy, ex - hx);
    curve(hx + Math.cos(a0) * 122, hy + Math.sin(a0) * 122, (hx + ex) / 2, (hy + ey) / 2 + (y < hy ? -30 : 30), ex, ey, p, rgba(col, 0.7), { lw: 2.5, nohead: true, dash: [8, 8], flow: t });
    card(x - 230, y - 60, 460, 120, col, p, () => { iconCircle(ic, x - 170, y, 34, col); T(n, x - 118, y - 18, { size: 30, w: 800 }); T(d, x - 118, y + 22, { size: 19, c: C.muted, w: 500 }); }, { hot: n === 'CALL-E' && t > S.at(0) + 5, nobar: true });
  });
  chipRow(['Collections & reminders', 'Customer service', 'KYC & verification', 'Telemarketing / leads', 'Quality assurance'], 960, 800, 16, C.teal, i => S.p(1, 0.3 + i * 0.7), { size: 25 });
  chipRow(['Banking & fintech', 'Insurance', 'E-commerce', 'Logistics', 'Telecom', 'BPO'], 960, 880, 14, C.blue, i => S.p(2, 0.2 + i * 0.45), { size: 21, w: 500 });
} });

/* 4 — Tech stack */
SC.push({ title: 'How a voice AI call works', lines: [
  { t: 'Under the hood, every voice call runs through a loop.' },
  { t: "Speech recognition, or ASR, turns the customer's voice into text.", s: "Speech recognition, or A.S.R., turns the customer's voice into text." },
  { t: 'Natural language understanding, or NLU, works out what they mean.', s: 'Natural language understanding, or N.L.U., works out what they mean.' },
  { t: 'Dialogue management, now enhanced with large language models, decides what to say next.' },
  { t: "Text-to-speech turns the reply back into a natural voice, with interruption handling, backchanneling like 'mm-hmm', and language switching." },
  { t: 'AI Rudder builds these core pieces in-house.' },
], draw(t, S) {
  const nodes = [['Customer', 'person', C.blue, 'voice'], ['ASR', 'chat', C.teal, 'speech → text'], ['NLU', 'gear', C.purple, 'text → meaning'], ['Dialogue + LLM', 'spark', C.orange, 'decide next step'], ['TTS', 'phone', C.green, 'text → voice']];
  const xs = [210, 580, 960, 1340, 1710], y = 400;
  const outs = ['🎙', '“Pagaré el viernes”', 'intent: promise_to_pay\ndate: Fri 9 Oct', '“¡Perfecto! El viernes 9…”', '🔊'];
  nodes.forEach(([n, ic, col, sub], i) => { const active = i === 0 ? S.t > S.at(0) : S.t > S.at(i); const p = i === 0 ? S.p(0, 0.2) : S.p(0, 0.4 + i * 0.25);
    const hot = (i === 0 && S.on(0)) || (i > 0 && S.on(i)) || (i === 4 && S.t > S.at(4));
    card(xs[i] - 150, y - 100, 300, 200, col, p, () => { iconCircle(ic, xs[i], y - 36, 34, col, { glow: hot }); T(n, xs[i], y + 34, { size: 30, w: 800, align: 'center' }); T(sub, xs[i], y + 70, { size: 20, c: C.muted, align: 'center', mono: true }); }, { hot, nobar: true });
    if (i < 4) { const ap = S.p(i === 0 ? 0 : i, i === 0 ? 0.8 : 0.1, 0.6); arrow(xs[i] + 152, y, xs[i + 1] - 158, y, i === 0 ? S.p(1, 0, .6) : S.p(i + 1, 0, 0.6), rgba(col, 0.9), { lw: 3 });
      const k = t - S.at(i + 1); if (k > 0) linePacket(xs[i] + 152, y, xs[i + 1] - 158, y, (k * 0.8) % 1, col, { r: 7 }); }
    // data sample under node
    if (i > 0 && i < 4) { const dp = S.p(i, 0.5, 0.8); const lines = outs[i].split('\n');
      pop(xs[i], y + 170, dp, () => { box(xs[i] - 165, y + 130, 330, 40 + lines.length * 30, { fill: 'rgba(4,16,24,0.85)', stroke: rgba(col, 0.45) });
        lines.forEach((l, j) => T(l, xs[i], y + 162 + j * 30, { size: 21, mono: i === 2, c: i === 2 ? col : C.text, align: 'center', w: 500 })); }); }
  });
  if (t > S.at(0) + 0.3) { wave(xs[0], y + 170, 200, 70, 14, t, C.blue, eo(P(t, S.at(0) + 0.3, .8))); }
  if (t > S.at(4)) { wave(xs[4], y + 170, 200, 70, 14, t + 1.3, C.green, eo(P(t, S.at(4), .8))); }
  // return loop
  curve(xs[4], y + 220, 960, y + 400, xs[0], y + 220, S.p(4, 0.4, 1.2), rgba(C.green, 0.7), { lw: 3, dash: [10, 10], flow: t });
  chipRow(['Interruption handling', "Backchanneling “mm-hmm”", 'Bilingual switching', 'Local accents'], 960, 760, 18, C.green, i => S.p(4, 1.5 + i * 0.7), { size: 24 });
  pop(960, 860, S.p(5, 0.1), () => { box(560, 826, 800, 68, { fill: rgba(C.orange, 0.15), stroke: C.orange, glow: rgba(C.orange, 0.5), r: 34 });
    T('Self-developed ASR · NLU · TTS  +  LLM-enhanced dialogue', 960, 861, { size: 26, w: 700, align: 'center', c: C.orange }); });
} });

/* 5 — CALL-E */
SC.push({ title: 'CALL-E: the goal-based phone agent', lines: [
  { t: "CALL-E is AI Rudder's goal-based phone agent." },
  { t: 'Instead of drawing a dialogue tree, you give it a goal in plain language, a phone number, and a result schema describing the data you want back.' },
  { t: 'CALL-E plans the call, asks for any missing details, dials, and handles voicemail, hold music and phone menus.' },
  { t: 'Then it returns a summary, a full transcript, and a structured result.' },
  { t: 'Developers reach it through an API, SDKs, a command-line tool, or MCP for AI agents.', s: 'Developers reach it through an A.P.I., S.D.K.s, a command-line tool, or M.C.P. for A.I. agents.' },
], draw(t, S) {
  const cx = 960, cy = 470;
  // core
  ring(cx, cy, 104, C.orange, t, { n: 3, spread: 70, a: 0.45, speed: 0.5 });
  pop(cx, cy, S.p(0, 0.1, 0.9), () => { ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, 104, 0, Math.PI * 2); ctx.fillStyle = '#1b1a14'; ctx.shadowColor = C.orange; ctx.shadowBlur = 70; ctx.fill(); ctx.restore();
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(t * 0.6); ctx.strokeStyle = C.orange; ctx.lineWidth = 3; ctx.setLineDash([30, 18]); ctx.beginPath(); ctx.arc(0, 0, 122, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
    T('CALL-E', cx, cy - 8, { size: 44, w: 900, align: 'center', c: C.orange, glow: C.orange, blur: 20 }); T('goal-based', cx, cy + 34, { size: 17, mono: true, c: C.muted, align: 'center' }); });
  // inputs
  const ins = [['Goal (task)', '“Remind María of her installment…”', C.teal], ['Phone · region · locale', '+52 55 •••• ••01 · MX · es-MX', C.blue], ['result_schema', '{ outcome: enum, promise_date, … }', C.purple]];
  ins.forEach(([h, d, col], i) => { const y = 250 + i * 160, p = S.p(1, 0.4 + i * 1.2);
    card(90, y, 470, 120, col, p, () => { T(h, 124, y + 40, { size: 28, w: 800 }); T(d, 124, y + 82, { size: 19, mono: true, c: col, w: 500 }); });
    curve(565, y + 60, 720, y + 60, cx - 128, cy, S.p(1, 1 + i * 1.2, .8), rgba(col, 0.8), { lw: 3 });
    const k = t - S.at(1) - 1.8 - i * 1.2; if (k > 0 && t < S.at(3)) packet(565, y + 60, 720, y + 60, cx - 128, cy, (k * 0.7) % 1, col, { r: 7 });
  });
  // orbit steps
  const steps = ['Plan', 'Clarify', 'Dial', 'Converse', 'Voicemail · hold · IVR'];
  const active = t > S.at(2) ? Math.floor((t - S.at(2)) / 1.2) % steps.length : -1;
  chipRow(steps.map((s, i) => ({ t: (i ? '→  ' : '') + s, on: i === active })), cx, 760, 18, C.yellow, i => S.p(2, i * 0.45), { size: 22 });
  // outputs
  const outs = [['Summary', 'Customer will pay Fri 9 Oct via SPEI.', C.green], ['Transcript', 'Agent: ¿Hablo con María…?  Cliente: Sí, soy yo…', C.teal], ['Structured result', '{ "outcome": "promise_to_pay", "promise_date": "2026-10-09", "certainty": "firm" }', C.orange]];
  outs.forEach(([h, d, col], i) => { const y = 250 + i * 160, p = S.p(3, i * 0.6);
    curve(cx + 128, cy, 1200, y + 60, 1355, y + 60, S.p(3, i * 0.6, .7), rgba(col, 0.8), { lw: 3 });
    card(1360, y, 480, 120, col, p, () => { T(h, 1394, y + 38, { size: 28, w: 800 }); const lines = wrap(typed(d, P(t, S.at(3) + i * 0.6 + 0.4, 1.4)), 420, 17, 500, true);
      lines.slice(0, 2).forEach((l, j) => T(l, 1394, y + 74 + j * 24, { size: 17, mono: true, c: col, w: 500 })); });
  });
  chipRow([{ t: 'REST API  POST /calls', icon: 'globe' }, { t: 'Python & TypeScript SDK', icon: 'gear' }, { t: 'calle CLI', icon: 'chat' }, { t: 'MCP: plan_call → run_call → get_call_run', icon: 'spark' }], 960, 850, 16, C.blue, i => S.p(4, 0.3 + i * 0.7), { size: 22 });
} });

/* 6 — Role */
SC.push({ title: 'The role: Technical CSM + Forward Deployed Engineer', lines: [
  { t: "You're interviewing for a hybrid role: Technical Customer Success Manager and Forward Deployed Engineer." },
  { t: 'The CSM side owns the customer relationship and the outcome. The FDE side sits with the customer and writes the code that makes the product work in their systems.', s: 'The C.S.M. side owns the customer relationship and the outcome. The F.D.E. side sits with the customer, and writes the code that makes the product work in their systems.' },
  { t: 'Together, you turn a business need into a working solution, connect systems and troubleshoot, test and interpret results, and explain trade-offs.' },
  { t: 'Your take-home was designed to show exactly those four skills. The orchestrator you built is classic forward-deployed work.' },
], draw(t, S) {
  const cx = 960, cy = 340;
  ring(cx, cy, 84, C.teal, t, { n: 3, spread: 80, a: 0.4 });
  pop(cx, cy, S.p(0, 0.1), () => { iconCircle('person', cx, cy, 84, C.teal, { glow: true, fillA: 0.2, lw: 4 }); T('Technical CSM + FDE', cx, cy + 128, { size: 36, w: 800, align: 'center' }); });
  chipRow([{ t: 'CSM: relationship · outcome · ROI', c: C.blue }, { t: 'FDE: code · integrations · deploy', c: C.orange }], 960, 524, 24, C.blue, i => S.p(1, i ? 3.2 : 0.3), { size: 20 });
  card(110, 250, 520, 190, C.blue, S.p(1, 0.2), () => { iconCircle('building', 190, 345, 44, C.blue); T('Customer', 260, 320, { size: 34, w: 800 }); T('business goals · systems', 260, 360, { size: 21, c: C.muted, w: 500 }); T('compliance · success metrics', 260, 392, { size: 21, c: C.muted, w: 500 }); });
  card(1290, 250, 520, 190, C.orange, S.p(1, 0.6), () => { iconCircle('spark', 1370, 345, 44, C.orange); T('AI Rudder', 1440, 320, { size: 34, w: 800 }); T('product · engineering', 1440, 360, { size: 21, c: C.muted, w: 500 }); T('CALL-E platform & roadmap', 1440, 392, { size: 21, c: C.muted, w: 500 }); });
  const bp = S.p(1, 1, 1);
  curve(635, 320, 790, 250, 870, 310, bp, rgba(C.blue, 0.8), { lw: 3 }); curve(1050, 310, 1130, 250, 1285, 320, bp, rgba(C.orange, 0.8), { lw: 3 });
  curve(1285, 380, 1130, 450, 1050, 380, bp, rgba(C.orange, 0.5), { lw: 2.5, dash: [8, 8], flow: t }); curve(870, 380, 790, 450, 635, 380, bp, rgba(C.blue, 0.5), { lw: 2.5, dash: [8, 8], flow: t });
  if (t > S.at(1) + 1.6) { const u = ((t - S.at(1)) * 0.5) % 1; packet(635, 320, 790, 250, 870, 310, u, C.blue, { r: 6 }); packet(1285, 380, 1130, 450, 1050, 380, u, C.orange, { r: 6 }); }
  const skills = [['1', 'Need → solution', 'Scope a customer problem and build the working workflow'], ['2', 'Connect & troubleshoot', 'APIs, webhooks, CRMs, failure handling in code'], ['3', 'Test & interpret', 'Automated tests, before/after, honest limits'], ['4', 'Explain trade-offs', 'Decisions, readiness, rollout plan']];
  skills.forEach(([n, h, d], i) => { const x = 110 + i * 432, y = 584;
    card(x, y, 400, 220, C.teal, S.p(2, i * 1.3), () => { badge(x + 50, y + 52, n, C.teal, true); T(h, x + 90, y + 52, { size: 25, w: 800 }); TW(d, x + 34, y + 102, 340, { size: 22, c: C.muted, w: 500 });
      if (t > S.at(3) + i * 0.3) pop(x + 360, y + 180, P(t, S.at(3) + i * 0.3, 0.5), () => iconCircle('check', x + 360, y + 180, 22, C.green, { glow: true })); });
  });
  pop(960, 862, S.p(3, 1.4), () => T('= your assignment: scenario (CSM) · orchestrator & tests (FDE) · decisions & rollout (both)', 960, 862, { size: 24, c: C.green, align: 'center', w: 600 }));
} });

/* 7 — Scenario */
SC.push({ title: 'Your scenario: Financiera Solaria', lines: [
  { t: 'Your scenario is Financiera Solaria, a fictional consumer lender in Mexico.' },
  { t: "Most late payers aren't unwilling. They forget, or they get paid after the due date." },
  { t: 'So the agent calls three days before an installment is due, and reminds them in Mexican Spanish.' },
  { t: 'Each call must end in one actionable CRM outcome, like a promise to pay on a specific date, with a task to verify it.', s: 'Each call must end in one actionable C.R.M. outcome, like a promise to pay on a specific date, with a task to verify it.' },
], draw(t, S) {
  card(96, 200, 560, 210, C.green, S.p(0, 0.2), () => {
    [C.green, '#f1f5f2', C.red].forEach((c, i) => box(134 + i * 22, 236, 22, 44, { fill: c, r: 2 }));
    T('Financiera Solaria', 216, 258, { size: 36, w: 800 }); T('Consumer lender · Mexico (fictional)', 134, 318, { size: 22, c: C.muted, w: 500 });
    T('8 customers · 5 time zones · es-MX', 134, 360, { size: 22, c: C.green, mono: true, w: 500 }); });
  chip(250, 470, 'They forget', C.yellow, S.p(1, 0.4), { icon: 'bell', size: 24 }); chip(510, 470, 'Paid after due date', C.yellow, S.p(1, 1.4), { icon: 'cal', size: 24 });
  // calendar
  const cx0 = 700, cy0 = 210, cw = 64; const cp = S.p(2, 0, 0.8);
  pop(cx0 + 224, cy0 + 220, cp, () => { box(cx0 - 10, cy0 - 10, 468, 460, { fill: 'rgba(8,24,34,0.92)', stroke: rgba(C.teal, .4) });
    T('October 2026', cx0 + 224, cy0 + 28, { size: 26, w: 800, align: 'center' });
    ['M', 'T', 'W', 'T', 'F', 'S', 'S'].forEach((d, i) => T(d, cx0 + 32 + i * cw, cy0 + 72, { size: 18, c: C.muted, align: 'center', mono: true }));
    for (let day = 1; day <= 31; day++) { const idx = day + 2; const col = idx % 7, row = Math.floor(idx / 7); const x = cx0 + 32 + col * cw, y = cy0 + 118 + row * 62;
      let c = C.text, f = null;
      if (day === 5) { f = C.teal; c = '#03141c'; } if (day === 8) { f = C.red; c = '#fff'; } if (day === 9 && t > S.at(3)) { f = C.green; c = '#03141c'; }
      if (f) { ctx.save(); ctx.beginPath(); ctx.arc(x, y, 24, 0, Math.PI * 2); ctx.fillStyle = f; ctx.shadowColor = f; ctx.shadowBlur = 20; ctx.fill(); ctx.restore(); }
      T(String(day), x, y + 1, { size: 22, c, align: 'center', w: f ? 800 : 500 }); }
    const k = S.p(2, 1.0, 1.2); const x5 = cx0 + 32 + 0 * cw, x8 = cx0 + 32 + 3 * cw, yy = cy0 + 118 + 1 * 62;
    curve(x8, yy - 26, (x5 + x8) / 2, yy - 62, x5, yy - 26, k, C.teal, { lw: 3 });
  });
  if (cp > 0) { [['due 8 Oct', C.red], ['call = due − 3', C.teal], ['promise 9 Oct', C.green]].forEach(([l, c], i) => { if (i === 2 && t < S.at(3)) return; chip([770, 935, 1080][i], i === 2 ? 760 : 700, l, c, P(t, S.at(2) + 0.6 + i * 0.3, .5) * (i === 2 ? S.p(3) : 1), { size: 20 }); }); }
  // chat
  const msgs = [['a', '¿Hablo con María Fernanda López García?', 0], ['c', 'Sí, soy yo.', 2.0], ['a', 'Le recuerdo su pago de $2,450 MXN, vence el 8 de octubre…', 3.4], ['c', 'El viernes nueve hago la transferencia por SPEI.', 0]];
  msgs.forEach(([who, m, off], i) => { const st = i < 3 ? S.at(2) + off : S.at(3) + 0.2; const p = P(t, st, 0.5); const isA = who === 'a';
    const lines = wrap(m, 470, 23, 500); const h = 36 + lines.length * 30, y = 220 + [0, 120, 220, 370][i]; const x = isA ? 1220 : 1820 - 520;
    pop(x + 260, y + h / 2, p, () => { box(x, y, 520, h, { fill: isA ? 'rgba(46,230,197,0.13)' : 'rgba(90,169,255,0.16)', stroke: rgba(isA ? C.teal : C.blue, .6), r: 22 });
      T(isA ? 'Sofía (AI)' : 'Cliente', x + 20, y - 12, { size: 16, c: isA ? C.teal : C.blue, mono: true });
      lines.forEach((l, j) => T(l, x + 20, y + 18 + j * 30, { size: 23, base: 'top', w: 500 })); }, { dx: isA ? -40 : 40, dy: 0 });
  });
  // CRM record
  card(96, 560, 560, 300, C.green, S.p(3, 1.4), () => { iconCircle('db', 150, 614, 28, C.green); T('CRM · ACC-1001', 196, 614, { size: 28, w: 800 });
    const rows = [['status', 'promise_to_pay', C.green], ['promise_date', '2026-10-09', C.text], ['task', 'verify_payment → collections_ops', C.teal], ['confirmed', 'CRM 201 created ✓', C.green]];
    rows.forEach(([k, v, c], i) => { const p = P(t, S.at(3) + 1.8 + i * 0.35, 0.5); T(k, 134, 680 + i * 44, { size: 20, mono: true, c: C.muted, a: p }); T(v, 330, 680 + i * 44, { size: 21, mono: true, c, a: p, w: 700 }); }); });
} });

/* 8 — Architecture */
SC.push({ title: 'The system you built, in 6 steps', lines: [
  { t: "Here's the system you built, in six steps." },
  { t: 'One: the orchestrator reads the account from the CRM, and guards check the phone, the do-not-call flag, and local calling hours.', s: 'One: the orchestrator reads the account from the C.R.M., and guards check the phone, the do-not-call flag, and local calling hours.' },
  { t: 'Two: it creates the call on CALL-E, with an idempotency key so nobody is ever called twice.' },
  { t: 'Three: CALL-E has the conversation, in Spanish.' },
  { t: "Four: CALL-E sends a webhook. Webhooks are unsigned, so it's only a wake-up signal." },
  { t: 'Five: the orchestrator re-reads the call from the authenticated API. That is the source of truth.', s: 'Five: the orchestrator re-reads the call from the authenticated A.P.I. That is the source of truth.' },
  { t: 'Six: business rules turn the result into a CRM status and a follow-up task, written through an outbox.', s: 'Six: business rules turn the result into a C.R.M. status and a follow-up task, written through an outbox.' },
], draw(t, S) {
  const step = [1, 2, 3, 4, 5, 6].map(i => t >= S.at(i));
  const cur = [1, 2, 3, 4, 5, 6].find(i => S.on(i)) || 0;
  // nodes
  card(110, 380, 260, 220, C.blue, S.p(0, 0.2), () => { iconCircle('db', 240, 450, 40, C.blue, { glow: cur === 1 || cur === 6 }); T('Mock CRM', 240, 530, { size: 30, w: 800, align: 'center' }); T(':8001 · Solaria', 240, 566, { size: 18, mono: true, c: C.muted, align: 'center' }); }, { nobar: true, hot: step[6] && t > S.at(6) + 2.6 });
  card(600, 250, 420, 480, C.teal, S.p(0, 0.5), () => { T('Orchestrator', 810, 296, { size: 34, w: 800, align: 'center' }); T('your code · :8000', 810, 334, { size: 18, mono: true, c: C.muted, align: 'center' });
    const subs = [['Guards', 'phone · DNC · 08–21 local', 1], ['Agent config', 'task + result_schema', 2], ['Webhook receiver', 'id check · dedupe', 4], ['Business rules', 'outcome → status + task', 6], ['Outbox', 'pending → synced', 6]];
    subs.forEach(([n, d, k], i) => { const on = cur === k || (k === 4 && cur === 5); const y = 370 + i * 68;
      box(622, y, 376, 56, { fill: on ? rgba(C.teal, .22) : 'rgba(255,255,255,0.03)', stroke: rgba(C.teal, on ? 1 : .3), lw: on ? 2.5 : 1.5, r: 12, glow: on ? rgba(C.teal, .5) : null });
      T(n, 640, y + 28, { size: 21, w: 700 }); T(d, 984, y + 28, { size: 14, mono: true, c: C.muted, align: 'right' }); }); }, { nobar: true });
  pop(1440, 490, S.p(0, 0.8), () => { ring(1440, 490, 86, C.orange, t, { n: 2, spread: 50, a: 0.4 }); ctx.save(); ctx.beginPath(); ctx.arc(1440, 490, 86, 0, Math.PI * 2); ctx.fillStyle = '#1b1a14'; ctx.shadowColor = C.orange; ctx.shadowBlur = cur === 3 ? 70 : 30; ctx.fill(); ctx.restore();
    T('CALL-E', 1440, 480, { size: 34, w: 900, align: 'center', c: C.orange }); T('API · voice', 1440, 516, { size: 17, mono: true, c: C.muted, align: 'center' }); });
  pop(1760, 490, S.p(0, 1.0), () => { iconCircle('phone', 1760, 490, 58, C.blue, { glow: cur === 3 }); T('Customer', 1760, 580, { size: 22, w: 700, align: 'center' }); });
  // flows
  const F = [
    [1, 375, 420, 615, 420, C.blue, 'GET /accounts'],
    [2, 1025, 410, 1355, 450, C.teal, 'POST /calls + Idempotency-Key'],
    [4, 1355, 525, 1025, 545, C.orange, 'webhook (unsigned) = signal only'],
    [5, 1025, 630, 1385, 565, C.green, 'GET /calls/{id} = source of truth'],
    [6, 615, 640, 375, 560, C.green, 'POST call-outcome'],
  ];
  F.forEach(([n, x1, y1, x2, y2, col, lab]) => { const p = S.p(n, 0.1, 0.8); arrow(x1, y1, x2, y2, p, col, { lw: 3.5, dash: n === 4 ? [12, 10] : null, flow: t });
    if (p > 0) { const mx = (x1 + x2) / 2, my = (y1 + y2) / 2; badge(mx, my, n, col, cur === n, p);
      T(lab, mx, my + (n === 2 || n === 1 ? -44 : n === 4 ? -40 : 46), { size: n >= 4 ? 16 : 18, mono: true, c: col, align: 'center', a: eo(p), w: 600 }); }
    if (cur === n) linePacket(x1, y1, x2, y2, ((t - S.at(n)) * 0.7) % 1, col, { r: 8 });
  });
  // step 3 conversation
  if (step[3]) { const p = S.p(3, 0, .6); ctx.save(); ctx.globalAlpha = eo(p); wave(1600, 490, 120, 60, 10, t, C.orange, 1); ctx.restore(); badge(1600, 400, 3, C.orange, cur === 3, p); T('es-MX conversation', 1600, 360, { size: 18, mono: true, c: C.orange, align: 'center', a: eo(p) }); }
  if (step[5]) pop(1440, 690, S.p(5, 1), () => iconCircle('shield', 1440, 650, 26, C.green, { glow: true }));
  if (step[6]) pop(240, 680, S.p(6, 2.4), () => chip(240, 680, '201 created ✓', C.green, 1, { size: 22, on: true }));
  if (step[1]) pop(240, 330, S.p(1, 1.5), () => chip(240, 330, 'name · amount · due · tz', C.blue, 1, { size: 18, mono: true }));
  if (step[2]) pop(1190, 320, S.p(2, 1.5), () => chip(1190, 320, 'key: solaria-reminder-2026-10-ACC-1001', C.teal, 1, { size: 15, mono: true }));
  chipRow(['blocked before CALL-E: no phone · do-not-call · 21:00+'], 810, 800, 0, C.red, () => S.p(1, 2.5), { size: 20, icon: 'lock' });
} });

/* 9 — Three layers */
SC.push({ title: 'Your core idea: three layers', lines: [
  { t: 'The core design idea is three layers.' },
  { t: 'Layer one, instructions: the task prompt. Purpose, AI disclosure, the identity check, and what the agent must never say.' },
  { t: "Layer two, workflow configuration: the result schema, with an 'unknown' option in every field, plus locale, metadata and the idempotency key." },
  { t: 'Layer three, external logic: code that decides who may be called, and what an answer actually means for the account.' },
  { t: 'In one sentence: the agent reports facts, and your code makes the decisions.' },
], draw(t, S) {
  const L = [['1', 'Instructions', 'the task prompt (agent_config.build_task)', ['Purpose + AI disclosure', 'Right-party check', 'Clarify vague date once', 'NEVER: threats, discounts, card data'], C.teal],
    ['2', 'Workflow configuration', 'the contract with CALL-E', ['result_schema (enum + unknown)', 'region MX · locale es-MX', 'metadata · account_id', 'Idempotency-Key'], C.blue],
    ['3', 'External logic', 'your tested code (guards.py · outcomes.py)', ['Who / when may be called', 'Is a promise really a promise?', 'Status + task + team', 'No auto-redial'], C.orange]];
  L.forEach(([n, h, sub, items, col], i) => { const y = 210 + i * 175, p = S.p(i + 1, 0, 0.9); const on = S.on(i + 1);
    if (p <= 0) return; ctx.save(); ctx.globalAlpha = eo(p); ctx.translate((1 - eo(p)) * -300, 0);
    ctx.save(); ctx.transform(1, 0, -0.18, 1, 0, 0); box(150 + y * 0.18, y, 1620, 150, { fill: rgba(col, on ? 0.18 : 0.09), stroke: rgba(col, on ? 1 : .5), lw: on ? 3 : 2, glow: on ? rgba(col, 0.45) : null, r: 18 }); ctx.restore();
    badge(170, y + 75, n, col, true);
    T(h, 220, y + 56, { size: 36, w: 800 }); T(sub, 220, y + 100, { size: 19, mono: true, c: C.muted });
    items.forEach((it, j) => { const pj = P(t, S.at(i + 1) + 1 + j * 0.5, 0.5); const cxp = 860 + (j % 2) * 440, cyp = y + 46 + Math.floor(j / 2) * 58; chip(cxp + 200, cyp, it, col, pj, { size: 20 }); });
    ctx.restore();
  });
  pop(960, 860, S.p(4, 0.1, .8), () => { box(320, 818, 1280, 84, { fill: 'rgba(8,22,30,0.95)', stroke: C.green, glow: rgba(C.green, 0.5), r: 42 });
    T('Agent reports facts', 690, 861, { size: 34, w: 800, align: 'center', c: C.teal }); arrow(900, 861, 1010, 861, S.p(4, 0.8, .5), C.green, { lw: 4 });
    T('Code makes decisions', 1240, 861, { size: 34, w: 800, align: 'center', c: C.orange, a: eo(S.p(4, 1.1, .6)) }); });
} });

/* 10 — Routing */
SC.push({ title: 'Every outcome → a named team', lines: [
  { t: 'Every outcome goes to a named team, with a clear status.' },
  { t: 'A firm promise with a real date becomes promise to pay, with a task to verify payment.' },
  { t: "A vague promise, like 'end of the month, if I get paid', becomes needs review for a human." },
  { t: 'Already paid goes to finance. A dispute goes to support. A request for a person becomes a high-priority callback.' },
  { t: 'And if the wrong person answers, the debt is never mentioned.' },
], draw(t, S) {
  const rows = [['“El viernes nueve, por SPEI”', 'firm promise', 'promise_to_pay', 'verify_payment → collections ops', C.green, 1, 0],
    ['“A fin de mes, si me pagan”', 'vague promise', 'needs_review', 'confirm_promise → agents', C.orange, 2, 0],
    ['“Ya pagué”', 'already paid', 'paid_claimed', 'reconcile → finance', C.blue, 3, 0],
    ['“Ese monto no es correcto”', 'dispute', 'dispute', 'ticket → support (high)', C.red, 3, 1.8],
    ['“Quiero hablar con una persona”', 'human requested', 'callback_requested', 'human_callback (high)', C.purple, 3, 3.6],
    ['Sister answers the phone', 'wrong person', 'wrong_party_contact', 'verify contact → data quality', C.muted, 4, 0]];
  const hx = [120, 780, 1290];
  ['WHAT THE CUSTOMER SAID', 'CRM STATUS', 'TASK → TEAM'].forEach((h, i) => T(h, hx[i], 214, { size: 18, mono: true, c: C.muted, ls: 2, a: eo(S.p(0, 0.3 + i * 0.3)) }));
  rows.forEach(([q, kind, st, task, col, li, off], i) => { const y = 248 + i * 100; const p0 = S.p(li, off, .6), p1 = S.p(li, off + .5, .6), p2 = S.p(li, off + 1, .6);
    card(hx[0], y, 560, 84, col, p0, () => { T(q, hx[0] + 36, y + 32, { size: 23, w: 600 }); T(kind, hx[0] + 36, y + 62, { size: 17, mono: true, c: col }); }, { dx: -40, dy: 0, noscale: true });
    arrow(hx[0] + 568, y + 42, hx[1] - 10, y + 42, p1, col, { lw: 3 });
    chip(hx[1] + 190, y + 42, st, col, p1, { size: 24, mono: true, w: 700, on: S.on(li) && P(t, S.at(li) + off, 1.5) < 1 });
    arrow(hx[1] + 395, y + 42, hx[2] - 10, y + 42, p2, col, { lw: 3 });
    card(hx[2], y + 6, 520, 72, col, p2, () => { T(task, hx[2] + 36, y + 42, { size: 22, w: 600 }); }, { dx: 40, dy: 0, noscale: true });
    if (i === 5 && p2 > 0) pop(hx[2] + 480, y + 42, P(t, S.at(4) + 1.6, .5), () => iconCircle('lock', hx[2] + 480, y + 42, 22, C.yellow, { glow: true }));
  });
} });

/* 11 — Outage */
SC.push({ title: 'When the CRM goes down', lines: [
  { t: 'Now the hard part: what if the CRM is down when the result arrives?', s: 'Now the hard part: what if the C.R.M. is down when the result arrives?' },
  { t: "Version one said 'synced' anyway, and silently lost the result." },
  { t: "Version two parks the write in an outbox, and honestly reports 'pending retry'." },
  { t: 'When the CRM is back, the outbox delivers it exactly once, even if the webhook arrives twice.', s: 'When the C.R.M. is back, the outbox delivers it exactly once, even if the webhook arrives twice.' },
  { t: 'Success only counts when the CRM itself confirms it.', s: 'Success only counts when the C.R.M. itself confirms it.' },
], draw(t, S) {
  const down = t > S.at(0) + 1.2 && t < S.at(3) + 0.6; const shake = down && t < S.at(0) + 1.8 ? Math.sin(t * 90) * 6 : 0;
  card(200, 220, 420, 150, C.teal, S.p(0, 0.1), () => { iconCircle('gear', 270, 295, 34, C.teal); T('Orchestrator', 320, 280, { size: 32, w: 800 }); T('call result arrived', 320, 318, { size: 19, mono: true, c: C.muted }); }, { nobar: true });
  ctx.save(); ctx.translate(shake, 0);
  card(1300, 220, 420, 150, down ? C.red : C.green, S.p(0, 0.3), () => { iconCircle('db', 1370, 295, 34, down ? C.red : C.green, { glow: true }); T('Mock CRM', 1420, 280, { size: 32, w: 800 });
    T(down ? '503 Service Unavailable' : (t > S.at(3) ? '201 created ✓' : 'online'), 1420, 318, { size: 19, mono: true, c: down ? C.red : C.green, w: 700 }); }, { nobar: true, hot: down || t > S.at(3) + 1 });
  ctx.restore();
  arrow(625, 295, 1295, 295, S.p(0, 0.5, .8), rgba(C.muted, .8), { lw: 3 });
  const k = t - S.at(0) - 0.5; if (k > 0 && k < 1.2) linePacket(625, 295, 1295, 295, k / 1.2, C.yellow, { r: 9 });
  if (down && t < S.at(1)) { const e = P(t, S.at(0) + 1.2, .5); ctx.save(); ctx.globalAlpha = 1 - e; ctx.strokeStyle = C.red; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(1290, 295, 10 + e * 70, 0, Math.PI * 2); ctx.stroke(); ctx.restore(); }
  // v1 panel
  card(120, 430, 800, 380, C.red, S.p(1, 0, .8), () => { T('v1 (first version)', 160, 486, { size: 26, mono: true, c: C.red, w: 700 });
    box(160, 530, 720, 80, { fill: 'rgba(255,255,255,0.04)', stroke: rgba(C.red, .4), r: 14 }); T('HTTP 200  “synced”', 200, 570, { size: 34, w: 800, mono: true });
    const xp = S.p(1, 1.2, .5); if (xp > 0) { ctx.save(); ctx.globalAlpha = eo(xp); ctx.strokeStyle = C.red; ctx.lineWidth = 6; ctx.beginPath(); ctx.moveTo(180, 570); ctx.lineTo(180 + 560 * eo(xp), 570); ctx.stroke(); ctx.restore(); }
    pop(520, 700, S.p(1, 1.8), () => { iconCircle('cross', 260, 700, 40, C.red, { glow: true }); T('Result silently lost', 320, 690, { size: 34, w: 800, c: C.red }); T('CALL-E never retries · nobody notices', 320, 734, { size: 20, c: C.muted, w: 500 }); });
  });
  // v2 panel
  card(1000, 430, 800, 380, C.green, S.p(2, 0, .8), () => { T('v2 (fixed)', 1040, 486, { size: 26, mono: true, c: C.green, w: 700 });
    chip(1220, 560, '202  crm_sync: pending_retry', C.orange, S.p(2, 0.8), { size: 22, mono: true });
    // outbox
    const ob = [1040, 610, 290, 170]; box(...ob, { fill: 'rgba(255,255,255,0.03)', stroke: rgba(C.yellow, .6), dash: [8, 6], r: 14 }); T('OUTBOX', 1080, 645, { size: 18, mono: true, c: C.yellow, ls: 2 });
    const inP = S.p(2, 1.4, .8), outP = S.p(3, 0.6, 1.2);
    if (inP > 0 && outP < 1) { const ex = lerp(lerp(1100, 1180, eo(inP)), 1520, eio(outP)), ey = lerp(720, 280, eio(outP)) ; pop(ex, ey, inP, () => { icon('mail', ex, ey, 54, C.yellow, 3); T(outP > 0 ? 'delivering…' : 'pending', ex + 44, ey, { size: 20, mono: true, c: C.yellow }); }); }
    if (t > S.at(3) + 1.8) { pop(1560, 660, S.p(3, 1.8), () => { iconCircle('check', 1410, 660, 30, C.green, { glow: true }); T('CRM 201 · 1 task', 1456, 660, { size: 28, w: 800, c: C.green }); }); }
    if (t > S.at(3) + 2.8) pop(1560, 740, S.p(3, 2.8), () => chip(1560, 740, 'webhook again → duplicate', C.blue, 1, { size: 17, mono: true }));
  });
  pop(960, 870, S.p(4, 0.1), () => { box(470, 835, 980, 70, { fill: 'rgba(8,22,30,0.96)', stroke: C.green, glow: rgba(C.green, .5), r: 35 }); T('Success = the CRM confirmed it. Nothing else.', 960, 871, { size: 30, w: 800, align: 'center', c: C.green }); });
} });

/* 12 — Tests */
SC.push({ title: 'Testing: v1 failed, v2 fixed', lines: [
  { t: 'Testing found two real bugs in version one.' },
  { t: "In test two, 'end of the month, if I get paid' was recorded as a firm promise." },
  { t: 'In test three, the CRM outage produced a false success.', s: 'In test three, the C.R.M. outage produced a false success.' },
  { t: 'Both were fixed with a deterministic promise rule and the outbox, and the retest passed everything.' },
  { t: 'That before-and-after story is your strongest evidence. Tell it.' },
], draw(t, S) {
  const rows = [['T1', 'Normal: firm promise'], ['T2', 'Ambiguous: “si me pagan”'], ['T3', 'Integration failure: CRM 503'], ['T4', 'Exception: asks for a human']];
  const v1 = ['pass', 'fail', 'fail', 'pass'], when = [0.6, null, null, 1.0];
  T('REQUIRED TEST', 200, 236, { size: 18, mono: true, c: C.muted, ls: 2, a: eo(S.p(0)) }); T('v1 · 270ed09', 1080, 236, { size: 18, mono: true, c: C.red, align: 'center', a: eo(S.p(0)) }); T('v2 · 24ac420', 1540, 236, { size: 18, mono: true, c: C.green, align: 'center', a: eo(S.p(3, 0.4)) });
  rows.forEach(([id, name], i) => { const y = 270 + i * 120;
    card(160, y, 720, 100, (i === 1 || i === 2) ? C.orange : C.teal, S.p(0, 0.2 + i * 0.25), () => { T(id, 210, y + 50, { size: 34, w: 900, mono: true, c: (i === 1 || i === 2) ? C.orange : C.teal }); T(name, 290, y + 50, { size: 28, w: 600 }); }, { noscale: true, dx: -40, dy: 0 });
    // v1 cell
    const st = v1[i] === 'pass' ? S.at(0) + when[i] : S.at(i === 1 ? 1 : 2) + 0.4; const p = P(t, st, .5); const col = v1[i] === 'pass' ? C.green : C.red;
    pop(1080, y + 50, p, () => { box(980, y + 10, 200, 80, { fill: rgba(col, .15), stroke: col, lw: 2.5, r: 40, glow: v1[i] === 'fail' ? rgba(col, .7) : null }); icon(v1[i] === 'pass' ? 'check' : 'cross', 1030, y + 50, 34, col, 4); T(v1[i].toUpperCase(), 1100, y + 51, { size: 26, w: 800, c: col, align: 'center' }); });
    if (v1[i] === 'fail' && t > st) ring(1080, y + 50, 50, C.red, t, { n: 2, spread: 40, a: 0.5, speed: 0.9 });
    // fix arrow + v2
    arrow(1190, y + 50, 1430, y + 50, S.p(3, 0.2 + i * 0.25, .6), rgba(C.green, .6), { lw: 3, dash: [8, 8], flow: t });
    pop(1540, y + 50, S.p(3, 1 + i * 0.4), () => { box(1440, y + 10, 200, 80, { fill: rgba(C.green, .15), stroke: C.green, lw: 2.5, r: 40 }); icon('check', 1490, y + 50, 34, C.green, 4); T('PASS', 1560, y + 51, { size: 26, w: 800, c: C.green, align: 'center' }); });
  });
  if (t > S.at(1)) pop(560, 800, S.p(1, 1.2), () => chip(560, 800, 'false promise → promise rule: specific date + firm + ≤ due+7d', C.orange, 1, { size: 20, mono: true }));
  if (t > S.at(2)) pop(560, 860, S.p(2, 0.8), () => chip(560, 860, 'false success → outbox + honest status', C.orange, 1, { size: 20, mono: true }));
  pop(1540, 805, S.p(3, 2.6), () => { const n = Math.round(33 * eo(S.p(3, 2.6, 1.5))); T(String(n), 1440, 805, { size: 84, w: 900, c: C.green, align: 'right', glow: C.green, blur: 24 }); T('automated tests', 1460, 787, { size: 24, w: 700 }); T('passing (pytest)', 1460, 823, { size: 24, w: 500, c: C.muted }); });
  if (t > S.at(4)) pop(1540, 896, S.p(4, 0.2), () => chip(1540, 896, 'Your strongest story: found → fixed → retested', C.yellow, 1, { size: 22, icon: 'star', on: true }));
} });

/* 13 — Decisions */
SC.push({ title: 'Three decisions to defend', lines: [
  { t: 'Be ready to defend three decisions.' },
  { t: "Decision one: business rules live in code, not in the prompt, because prompts are probabilistic and money decisions shouldn't be." },
  { t: 'Decision two: treat the webhook as a signal, re-read the truth from the API, and write through an idempotent outbox.', s: 'Decision two: treat the webhook as a signal, re-read the truth from the A.P.I., and write through an idempotent outbox.' },
  { t: 'Decision three: keep the scope narrow. One reminder, no negotiation, no automatic redial. Anything that needs judgment becomes a human task.' },
  { t: 'For each one, know the problem, the alternatives, the trade-off, and what would change your mind.' },
], draw(t, S) {
  const D = [['D1', 'Rules in code, not the prompt', 'The agent reports facts in a typed schema. Deterministic rules decide status and task.', 'gear', C.teal, 'Evidence: T2 failed in v1, passes in v2'],
    ['D2', 'Webhook = signal, API = truth', 'Unsigned webhook only wakes us up. Re-read from the API. Idempotent outbox to the CRM.', 'shield', C.blue, 'Evidence: outage test, forged-webhook test'],
    ['D3', 'Narrow scope', 'One reminder. No negotiation, no payments, no auto-redial. Judgment → routed human task.', 'lock', C.orange, 'Evidence: every non-happy path → named task']];
  D.forEach(([id, h, d, ic, col, ev], i) => { const x = 120 + i * 570, y = 220, p = S.p(i + 1, 0, 0.9); if (p <= 0) return; const on = S.on(i + 1);
    ctx.save(); const sx = eo(p); ctx.translate(x + 260, 0); ctx.scale(Math.max(0.01, sx), 1); ctx.translate(-(x + 260), 0); ctx.globalAlpha = clamp(p * 2);
    box(x, y, 520, 500, { fill: C.card, stroke: rgba(col, on ? 1 : .5), lw: on ? 3 : 2, glow: on ? rgba(col, .5) : null, r: 24 });
    iconCircle(ic, x + 80, y + 85, 46, col, { glow: on }); T(id, x + 470, y + 85, { size: 54, w: 900, c: rgba(col, .9), align: 'right', mono: true });
    TW(h, x + 40, y + 165, 450, { size: 34, w: 800, lh: 42 }); TW(d, x + 40, y + 270, 450, { size: 24, w: 500, c: C.muted, lh: 34 });
    box(x + 30, y + 420, 460, 54, { fill: rgba(col, .12), r: 12 }); T(ev, x + 50, y + 447, { size: 18, mono: true, c: col });
    ctx.restore(); });
  const chain = ['Problem', 'Alternatives', 'Why', 'Evidence', 'Trade-off', 'What would change my mind'];
  chipRow(chain, 960, 800, 14, C.yellow, i => S.p(4, 0.2 + i * 0.45), { size: 22 });
  if (t > S.at(4)) for (let i = 0; i < 5; i++) {} // (chips carry the message)
} });

/* 14 — Rollout */
SC.push({ title: 'Ready? Rollout & metrics', lines: [
  { t: 'Is it ready? Yes, for a controlled pilot after a short pre-pilot. Not yet for full volume.' },
  { t: 'Two blockers: live Spanish extraction accuracy is unproven, and Mexico runs on an international line, intended mainly for testing.' },
  { t: 'Phase one is a pre-pilot of 30 to 50 internal calls. Phase two is a four-week pilot on up to a thousand accounts, compared against SMS only.', s: 'Phase one is a pre-pilot of thirty to fifty internal calls. Phase two is a four-week pilot on up to a thousand accounts, compared against S.M.S. only.' },
  { t: 'Track right-party contact, early hang-ups, extraction accuracy against human labels, and above all, the promise-kept rate.' },
], draw(t, S) {
  pop(700, 240, S.p(0, 0.2), () => chip(700, 240, 'Controlled pilot: YES', C.green, 1, { size: 30, icon: 'check', on: true }));
  pop(1240, 240, S.p(0, 2.2), () => chip(1240, 240, 'Full volume: NOT YET', C.red, 1, { size: 30, icon: 'cross' }));
  chipRow([{ t: 'Live Spanish extraction accuracy unproven', icon: 'warn' }, { t: 'MX = international line (dev/test)', icon: 'warn' }], 960, 330, 24, C.orange, i => S.p(1, 0.6 + i * 2.6), { size: 23 });
  // timeline
  const y = 500, x0 = 200, x1 = 1720; const tp = S.p(2, 0, S.d - S.at(2) - 1);
  box(x0, y - 4, x1 - x0, 8, { fill: 'rgba(143,169,182,0.18)', r: 4 }); box(x0, y - 4, (x1 - x0) * eo(tp), 8, { fill: C.teal, r: 4, glow: C.teal, blur: 20 });
  const ph = [['Pre-pilot', '1–2 weeks', '30–50 internal calls · accuracy vs human labels · legal review', 0.1, C.teal], ['Pilot', '4 weeks', '500–1,000 low-risk accounts · A/B vs SMS-only · QA on needs_review', 3.6, C.blue], ['Expand', 'only if targets met', '2 billing cycles beat control · no compliance incidents', 7.5, C.green]];
  ph.forEach(([n, d, det, off, col], i) => { const x = x0 + 120 + i * 640, p = S.p(2, off, .7);
    pop(x, y, p, () => { ctx.save(); ctx.beginPath(); ctx.arc(x, y, 20, 0, Math.PI * 2); ctx.fillStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 26; ctx.fill(); ctx.restore(); });
    card(x - 220, y + 40, 470, 170, col, p, () => { T(n, x - 186, y + 82, { size: 32, w: 800 }); T(d, x + 230, y + 82, { size: 19, mono: true, c: col, align: 'right' }); TW(det, x - 186, y + 112, 420, { size: 20, c: C.muted, w: 500, lh: 27 }); });
  });
  // gauges
  const G = [['Right-party contact', '≥ 35%', 0.35, C.teal], ['Early hang-ups', '≤ 25%', 0.25, C.orange], ['Extraction accuracy', '≥ 95%', 0.95, C.blue], ['Promise-kept rate', '> SMS-only', 0.7, C.green]];
  G.forEach(([n, tg, v, col], i) => { const cx = 330 + i * 420, cy = 845, p = S.p(3, 0.3 + i * 0.9, 1.2); if (p <= 0) return;
    ctx.save(); ctx.globalAlpha = clamp(p * 2); ctx.lineCap = 'round'; ctx.lineWidth = 12; ctx.strokeStyle = 'rgba(143,169,182,0.2)'; ctx.beginPath(); ctx.arc(cx, cy, 70, Math.PI, 2 * Math.PI); ctx.stroke();
    ctx.strokeStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 16; ctx.beginPath(); ctx.arc(cx, cy, 70, Math.PI, Math.PI + Math.PI * v * eo(p)); ctx.stroke(); ctx.restore();
    T(tg, cx, cy - 18, { size: 22, w: 800, align: 'center', c: col, a: eo(p) }); T(n, cx, cy + 30, { size: 21, w: 600, align: 'center', a: eo(p) });
    if (i === 3 && t > S.at(3) + 4) ring(cx, cy - 20, 70, C.green, t, { n: 2, spread: 40, a: 0.5 }); });
} });

/* 15 — STAR + close */
SC.push({ title: 'STAR answers & your closing line', lines: [
  { t: 'For behavioral questions, use STAR: situation, task, action, result.' },
  { t: 'Be specific. Use real numbers, name the stakeholders, and say what you learned.' },
  { t: 'Prepare a few questions for them, about customers, the team, and how CALL-E is evolving.' },
  { t: 'And remember your one-line thesis.' },
  { t: "You built an honest workflow. It never records an outcome that didn't happen, and never reports a CRM update that didn't land. Good luck!", s: "You built an honest workflow. It never records an outcome that didn't happen, and never reports a C.R.M. update that didn't land. Good luck!" },
], draw(t, S) {
  const L = [['S', 'Situation', C.teal], ['T', 'Task', C.blue], ['A', 'Action', C.purple], ['R', 'Result', C.orange]];
  L.forEach(([l, w, col], i) => { const x = 330 + i * 420, y = 330, p = S.p(0, 1.2 + i * 0.6, .8); if (p <= 0) return;
    ctx.save(); ctx.translate(x, y); ctx.scale(1, Math.max(0.01, eo(p))); ctx.translate(-x, -y); ctx.globalAlpha = clamp(p * 2);
    box(x - 170, y - 110, 340, 220, { fill: C.card, stroke: col, lw: 2.5, glow: rgba(col, .45), r: 24 }); T(l, x, y - 22, { size: 110, w: 900, c: col, align: 'center', glow: col, blur: 20 }); T(w, x, y + 70, { size: 30, w: 700, align: 'center' }); ctx.restore(); });
  chipRow(['numbers', 'stakeholders', 'tools & systems', 'business impact', 'lessons learned'], 960, 520, 14, C.teal, i => S.p(1, 0.3 + i * 0.4), { size: 23 });
  const g = P(t, S.d - 2.6, 0.6);
  if (g < 1) { ctx.save(); ctx.globalAlpha = 1 - g; pop(960, 600, S.p(2, 0.2), () => chip(960, 600, 'Bring 3–5 questions for them', C.yellow, 1, { size: 24, icon: 'q' })); ctx.restore(); }
  const q = "“I built an honest workflow: it never records an outcome that didn't happen, and never reports a CRM update that didn't land.”";
  pop(960, 780, S.p(3, 0.2), () => { box(200, 690, 1520, 180, { fill: 'rgba(8,22,30,0.96)', stroke: C.green, glow: rgba(C.green, .5), r: 26 });
    const lines = wrap(typed(q, P(t, S.at(4), (S.at(4) + 9 > S.d ? S.d - S.at(4) - 2 : 7))), 1400, 36, 700);
    lines.forEach((l, i) => T(l, 960, 750 + i * 52, { size: 36, w: 700, align: 'center' }));
    if (t < S.at(4)) T('your one-line thesis…', 960, 780, { size: 28, c: C.muted, align: 'center', mono: true }); });
  if (g > 0) { T('Good luck!', 960, 600, { size: 64, w: 900, align: 'center', c: C.orange, glow: C.orange, blur: 30, a: eo(g) });
    const R2 = rng(9); for (let i = 0; i < 60; i++) { const a = R2() * Math.PI * 2, sp = 200 + R2() * 500, k = (t - (S.d - 2.6)); if (k < 0) break; const x = 960 + Math.cos(a) * sp * k, y = 600 + Math.sin(a) * sp * k + 200 * k * k;
      ctx.save(); ctx.globalAlpha = clamp(1 - k / 2.6); ctx.fillStyle = [C.teal, C.orange, C.yellow, C.blue, C.pink][i % 5]; ctx.fillRect(x, y, 10, 6); ctx.restore(); } }
} });

/* ---------- timeline ---------- */
const LEAD = 0.8, GAP = 0.35, TAIL = 1.1;
function estimateTimeline() {
  let T0 = 0; const scenes = SC.map(sc => { let tt = LEAD; const lines = sc.lines.map(l => { const d = Math.max(1.6, (l.s || l.t).length / 15); const o = { start: tt, dur: d }; tt += d + GAP; return o; });
    const s = { start: T0, dur: tt - GAP + TAIL, lines }; T0 += s.dur; return s; });
  return { total: T0, scenes };
}
let TL = window.TIMELINE || estimateTimeline();
function setTimeline(tl) { TL = tl; }

/* ---------- frame ---------- */
function caption(text, a) {
  if (!text || a <= 0) return; const lines = wrap(text, 1500, 30, 500); const h = lines.length * 40 + 26; const w = Math.max(...lines.map(l => MW(l, 30, 500))) + 60; const y = H - 62 - h;
  ctx.save(); ctx.globalAlpha = a; box(W / 2 - w / 2, y, w, h, { fill: 'rgba(2,10,15,0.78)', r: 14 });
  lines.forEach((l, i) => T(l, W / 2, y + 13 + 20 + i * 40, { size: 30, w: 500, align: 'center' })); ctx.restore();
}
function renderAt(T0, opts = {}) {
  T0 = clamp(T0, 0, TL.total - 1e-3);
  let i = TL.scenes.findIndex(s => T0 >= s.start && T0 < s.start + s.dur); if (i < 0) i = TL.scenes.length - 1;
  const sc = SC[i], tm = TL.scenes[i], t = T0 - tm.start; const S = mkS(tm, t);
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; bg(T0);
  const ain = eo(P(t, 0, 0.6)), aout = 1 - P(t, tm.dur - 0.45, 0.45);
  ctx.save(); ctx.globalAlpha = ain * aout; const z = lerp(1.025, 1, eo(P(t, 0, 0.9))); ctx.translate(W / 2, H / 2); ctx.scale(z, z); ctx.translate(-W / 2, -H / 2);
  sc.draw(t, S); ctx.restore();
  if (!sc.noHeader) { ctx.save(); ctx.globalAlpha = aout; header(i + 1, SC.length, sc.title, t); ctx.restore(); }
  // wipe between scenes
  const wp = P(t, tm.dur - 0.4, 0.4), wi = 1 - P(t, 0, 0.35);
  const wk = wp > 0 ? wp * 0.5 : (i > 0 ? 0.5 + (1 - wi) * 0.5 : 2); if (wk <= 1) { const x = lerp(-600, W + 600, wk); ctx.save(); const g = ctx.createLinearGradient(x - 300, 0, x + 300, 0);
    g.addColorStop(0, 'rgba(46,230,197,0)'); g.addColorStop(0.5, 'rgba(46,230,197,0.22)'); g.addColorStop(1, 'rgba(46,230,197,0)'); ctx.fillStyle = g; ctx.transform(1, 0, -0.3, 1, 160, 0); ctx.fillRect(x - 300, 0, 600, H); ctx.restore(); }
  // captions
  if (opts.captions !== false) { const li = tm.lines.findIndex((l, j) => t >= l.start - 0.1 && t < (j + 1 < tm.lines.length ? tm.lines[j + 1].start - 0.1 : tm.dur - 0.3));
    if (li >= 0) { const l = tm.lines[li]; const a = Math.min(eo(P(t, l.start - 0.1, 0.25)), 1); caption(sc.lines[li].t, a); } }
  // progress
  box(0, H - 6, W * (T0 / TL.total), 6, { fill: C.teal, r: 0, glow: C.teal, blur: 12 });
}
function init(canvas) { ctx = canvas.getContext('2d'); }
window.MOTION = { W, H, SC, init, renderAt, setTimeline, get timeline() { return TL; }, lines: () => SC.map(s => s.lines.map(l => ({ t: l.t, s: l.s || l.t }))) };
})();
