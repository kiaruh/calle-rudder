// Renders engine.js into an MP4 with a macOS `say` voiceover, synced sentence by sentence.
// Usage:
//   node build.mjs --puppeteer <path/to/node_modules/puppeteer-core> --ffmpeg <ffmpeg binary> [--out file.mp4] [--tmp dir]
//   add --stills 12,40,95 to only write PNG stills at those seconds (for checking layouts).
import { createRequire } from 'node:module';
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, arr) => (v.startsWith('--') ? [...a, [v.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]] : a), []));
const require = createRequire(import.meta.url);
const puppeteer = require(args.puppeteer || 'puppeteer-core');
const FFMPEG = args.ffmpeg || 'ffmpeg';
const OUT = path.resolve(args.out || path.join(HERE, '..', 'ai-rudder-explainer.mp4'));
const TMP = path.resolve(args.tmp || path.join(os.tmpdir(), 'rudder-video'));
const FPS = Number(args.fps || 30), VOICE = args.voice || 'Samantha', RATE = String(args.rate || 182), SR = 48000;
const LEAD = 0.8, GAP = 0.35, TAIL = 1.1;
const CHROME = args.chrome || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
fs.mkdirSync(TMP, { recursive: true });

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--allow-file-access-from-files', '--force-device-scale-factor=1'] });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
page.on('pageerror', e => console.error('PAGE ERROR', e.message));
page.on('console', m => { if (m.type() === 'error') console.error('CONSOLE', m.text()); });
await page.goto(pathToFileURL(path.join(HERE, 'player.html')).href + '?render', { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);

if (args.stills) {
  for (const s of String(args.stills).split(',').map(Number)) {
    if (fs.existsSync(path.join(HERE, 'timeline.js'))) { /* timeline.js already loaded by the page */ }
    await page.evaluate(t => window.renderFrame(t), s);
    const el = await page.$('#c'); await el.screenshot({ path: path.join(TMP, `still_${s}.png`) });
    console.log('still', path.join(TMP, `still_${s}.png`));
  }
  await browser.close(); process.exit(0);
}

// 1) narration per sentence
const scenes = await page.evaluate(() => MOTION.lines());
function speak(text) {
  const h = crypto.createHash('sha1').update(VOICE + RATE + text).digest('hex').slice(0, 16);
  const aiff = path.join(TMP, h + '.aiff'), pcm = path.join(TMP, h + '.pcm');
  if (!fs.existsSync(pcm)) {
    let r = spawnSync('say', ['-v', VOICE, '-r', RATE, '-o', aiff, text]); if (r.status) throw new Error('say failed: ' + r.stderr);
    r = spawnSync(FFMPEG, ['-y', '-loglevel', 'error', '-i', aiff, '-ar', String(SR), '-ac', '1', '-f', 's16le', pcm]); if (r.status) throw new Error('ffmpeg pcm failed: ' + r.stderr);
  }
  return fs.readFileSync(pcm);
}
let T0 = 0; const clips = []; const tl = { total: 0, scenes: [] };
for (const [si, sc] of scenes.entries()) {
  let tt = LEAD; const lines = [];
  for (const l of sc) { const pcm = speak(l.s); const dur = pcm.length / 2 / SR; clips.push([T0 + tt, pcm]); lines.push({ start: +tt.toFixed(3), dur: +dur.toFixed(3) }); tt += dur + GAP; }
  const dur = tt - GAP + TAIL + (si === scenes.length - 1 ? 2.5 : 0); tl.scenes.push({ start: +T0.toFixed(3), dur: +dur.toFixed(3), lines }); T0 += dur;
}
tl.total = +T0.toFixed(3);
console.log(`narration: ${clips.length} sentences, ${tl.total.toFixed(1)} s`);

// 2) assemble one PCM track, write wav + m4a + timeline.js
const nS = Math.ceil(tl.total * SR); const buf = Buffer.alloc(nS * 2);
for (const [st, pcm] of clips) pcm.copy(buf, Math.round(st * SR) * 2, 0, Math.min(pcm.length, buf.length - Math.round(st * SR) * 2));
const hdr = Buffer.alloc(44); hdr.write('RIFF', 0); hdr.writeUInt32LE(36 + buf.length, 4); hdr.write('WAVE', 8); hdr.write('fmt ', 12); hdr.writeUInt32LE(16, 16); hdr.writeUInt16LE(1, 20); hdr.writeUInt16LE(1, 22);
hdr.writeUInt32LE(SR, 24); hdr.writeUInt32LE(SR * 2, 28); hdr.writeUInt16LE(2, 32); hdr.writeUInt16LE(16, 34); hdr.write('data', 36); hdr.writeUInt32LE(buf.length, 40);
const WAV = path.join(TMP, 'narration.wav'); fs.writeFileSync(WAV, Buffer.concat([hdr, buf]));
spawnSync(FFMPEG, ['-y', '-loglevel', 'error', '-i', WAV, '-c:a', 'aac', '-b:a', '128k', path.join(HERE, 'narration.m4a')]);
fs.writeFileSync(path.join(HERE, 'timeline.js'), 'window.TIMELINE = ' + JSON.stringify(tl) + ';\n');
await page.evaluate(t => MOTION.setTimeline(t), tl);
if (args['audio-only']) { await browser.close(); console.log('timeline.js + narration.m4a written'); process.exit(0); }

// 3) frames → ffmpeg
const N = Math.ceil(tl.total * FPS);
const ff = spawn(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-i', WAV,
  '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', '-shortest', OUT], { stdio: ['pipe', 'inherit', 'inherit'] });
const done = new Promise((res, rej) => ff.on('exit', c => c ? rej(new Error('ffmpeg exit ' + c)) : res()));
const t0 = Date.now();
for (let f = 0; f < N; f++) {
  const b64 = await page.evaluate(t => { window.renderFrame(t); return document.getElementById('c').toDataURL('image/jpeg', 0.93).split(',')[1]; }, f / FPS);
  if (!ff.stdin.write(Buffer.from(b64, 'base64'))) await new Promise(r => ff.stdin.once('drain', r));
  if (f % 300 === 0) console.log(`frame ${f}/${N}  ${((Date.now() - t0) / 1000).toFixed(0)}s`);
}
ff.stdin.end(); await done; await browser.close();
console.log('wrote', OUT);
