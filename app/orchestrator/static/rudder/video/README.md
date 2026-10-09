# Explainer video source

- `engine.js`: the 15 animated chapters (canvas motion graphics + narration text). Rendering is a pure function of time.
- `player.html`: interactive version in the browser (play, scrub). Uses `timeline.js` + `narration.m4a` when present.
- `build.mjs`: renders `../ai-rudder-explainer.mp4`. It voices each sentence with macOS `say` (Samantha), times every
  animation cue and caption to the real audio, captures frames from headless Chrome, and encodes with ffmpeg.

Rebuild (needs Google Chrome, `npm i puppeteer-core`, and an ffmpeg binary):

```bash
node build.mjs --puppeteer /path/to/node_modules/puppeteer-core --ffmpeg /path/to/ffmpeg
```

Add `--stills 12,40,95` to only write PNG frames at those seconds, or `--audio-only` to regenerate narration and timing.
