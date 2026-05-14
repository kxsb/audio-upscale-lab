
# `ROADMAP.md`

# Audio Upscale Lab — Roadmap

This roadmap tracks the evolution of **Audio Upscale Lab** from a functional local prototype into a more complete AI audio restoration and evaluation environment.

The project is intentionally exploratory. Its purpose is not only to process audio, but to understand:

- what AI restoration models actually add;
- when those changes are musically useful;
- when they merely shift the tonal balance or add artificial texture;
- how objective metrics and subjective listening can be combined.

---

# Current milestone — Prototype foundation

## ✅ V1 — Local project pipeline

### Implemented

- PyWebView desktop shell
- Modern local UI
- YouTube URL input
- `yt-dlp` source extraction
- Deno / EJS support detection
- Local project folder creation
- Source stream archiving
- 48 kHz / 24-bit WAV reference generation
- Project metadata persistence in `project.json`
- Runtime dependency checks in the interface

---

## ✅ V2 — AudioSR processing engine

### Implemented

- AudioSR job runner integrated into the app
- Background job execution
- Job status polling in the UI
- Per-chunk progress monitoring
- GUI settings for:
  - guidance scale;
  - input cutoff;
  - DDIM steps;
  - seed;
  - chunk size;
  - overlap;
  - multiband ensemble.
- Stereo treatment, chunk overlap and crossfade
- Temp-file handling compatible with Windows
- Trimming fix to avoid unwanted silent tails
- Output metadata appended to project history

---

## ✅ V3 — Comparative analysis engine

### Implemented

- Reference vs processed comparison
- Time alignment verification
- Global signal diagnostics
- Loudness / RMS / peak measurements
- Stereo and mid-side diagnostics
- Spectral centroid / rolloff / flatness tracking
- Energy analysis by frequency band
- High-frequency summaries
- Residual metrics
- Difference WAV export
- High-frequency residual WAV export
- Graph generation:
  - mean spectrum comparison;
  - spectral delta;
  - energy delta by band;
  - relative band energy;
  - original / processed spectrograms;
  - residual spectrograms;
  - high-frequency zooms;
  - temporal residual RMS plot.
- JSON and CSV reports
- Initial metric summary shown in the app

---

# Immediate next steps

## 🚧 V3.1 — Display analysis graphs inside the UI

### Goal
Make the app immediately informative without requiring the user to open folders manually.

### Planned

- Display generated PNG graphs directly in the interface
- Thumbnail grid for all analysis figures
- Click-to-expand modal view
- Group graphs by category:
  - overall spectrum;
  - high-frequency extension;
  - residual analysis;
  - temporal artifacts.
- Better visual reading of the generated report

### Why it matters
The current analysis engine is powerful, but the most meaningful visual information lives in the project folder. Bringing it into the UI will turn the app from a processing shell into a true diagnostic cockpit.

---

## 🚧 V3.2 — Integrated A/B listening

### Goal
Let the user assess outputs without leaving the app.

### Planned

- Embedded audio player for:
  - reference WAV;
  - processed render;
  - full residual;
  - high-frequency residual.
- A/B synchronized playback
- Instant mute / demute switching
- Optional loudness-matched comparison
- Loop selection for critical listening
- Keyboard shortcuts for blind-ish comparison

### Why it matters
Analysis alone is not enough. Audio restoration is ultimately judged by listening. The app should make it easy to hear exactly what the graphs describe.

---

## 🚧 V3.3 — Analysis summary interpretation layer

### Goal
Translate raw measurements into readable diagnostics.

### Planned

- Automatic textual interpretation such as:
  - “High-frequency extension is marked.”
  - “Tonal balance shifts toward the treble.”
  - “Residual is highly concentrated above 12 kHz.”
  - “Stereo image remains stable.”
- Detection of possible warning patterns:
  - strong brightening;
  - excessive HF residual;
  - suspected over-sharpening;
  - possible chunk-boundary artifacts;
  - unexpected low-frequency drift.
- Basic quality heuristic labels:
  - conservative;
  - moderate;
  - aggressive;
  - suspicious.

---

# Upscale experimentation roadmap

## 🚧 V4 — Multi-render experimentation

### Goal
Compare multiple AudioSR settings for the same source.

### Planned

- Launch multiple renders with different presets
- Preset library:
  - subtle;
  - balanced;
  - aggressive;
  - multiband conservative;
  - experimental.
- Persist render settings and analyses
- Comparison matrix across renders
- Quick ranking by metrics
- Side-by-side graph comparison
- One-click A/B/C listening

### Key question
Which parameters genuinely improve perceived quality, and which merely intensify treble reconstruction?

---

## 🚧 V4.1 — Better AudioSR parameter exploration

### Planned experiments

- Systematically test:
  - cutoff 12 / 14 / 16 kHz;
  - guidance scale 1.5–4.0;
  - multiband on / off;
  - different chunk lengths and overlaps;
  - fixed vs random seed.
- Compare outputs using the integrated analysis engine
- Capture subjective listening notes manually in the UI

### Expected outcome
Build an empirical map of how AudioSR behaves across different source types and genres.

---

# Quality estimation roadmap

## 🚧 V5 — Upscale plausibility scoring

### Goal
Provide a non-authoritative but useful indicator of whether a rendered upscale looks technically and musically plausible.

### Planned score families

#### 1. Integrity score
Checks that the process did not structurally damage the file:

- duration drift;
- alignment errors;
- clipping;
- loudness jumps;
- stereo collapse;
- chunk-boundary anomalies;
- unexpected residual bursts.

#### 2. Spectral enrichment score
Estimates whether the processing truly extends the spectrum:

- HF energy reconstruction;
- rolloff extension;
- centroid movement;
- gain by high-frequency band;
- absolute weight of reconstructed energy.

#### 3. Tonal balance shift score
Detects when an upscale behaves more like a treble remaster than an enrichment process:

- tilt toward high frequencies;
- disproportionate gain in 8–20 kHz zones;
- low / mid band weakening;
- high spectral flatness increase.

#### 4. Residual naturality score
Attempts to distinguish structured additions from diffuse synthetic artifacts:

- residual concentration over time;
- correlation with musical events;
- distribution of residual power;
- noise-like vs structured HF material.

### Important limitation
No metric can currently replace human listening for this task. The intended score should be presented as:

> **“quality likelihood / plausibility indicator”**

not as a definitive truth.

---

## 🚧 V5.1 — Personal preference learning

### Goal
Train the tool to anticipate the user’s taste.

### Planned

- Let the user mark renders as:
  - better;
  - worse;
  - equivalent;
  - too bright;
  - too artificial;
  - interesting but not preferable.
- Store subjective judgments alongside objective metrics
- Build a simple preference ranking model over time
- Estimate:
  - “likely preferred by this user”;
  - “likely over-bright according to past judgments”.

### Why it matters
Audio taste is not universal. A useful assistant should eventually learn what kinds of changes are actually perceived as improvements by its user.

---

# Alternative restoration engines

## 🚧 V6 — Plugin-like processing engines

### Goal
Turn Audio Upscale Lab into a modular restoration laboratory.

### Candidate engines / directions

- AudioSR — high-frequency reconstruction
- Apollo — lossy music repair experiments
- BABE-2 — generative restoration / equalization experiments
- Diffusion-based restoration tools
- Future models oriented toward global enrichment or mastering-style restoration

### Planned architecture

Each engine should expose:

- name and purpose;
- settings schema;
- supported input constraints;
- run method;
- output artifact path;
- analysis compatibility.

The UI should then present engines as selectable treatment modules.

---

## 🚧 V6.1 — Global enrichment vs high-frequency extension

### Motivation
Initial AudioSR experiments suggest a key limitation:

> The model can meaningfully reconstruct upper-spectrum content, but it may shift the tonal centre upward rather than making the track feel globally richer or deeper.

### Planned research questions

- Can another model improve perceived body and amplitude without merely brightening the mix?
- Can a multi-engine chain produce a more balanced result?
- Is a parallel/blended architecture preferable to sequential processing?

---

## 🚧 V6.2 — Low-frequency / bass-oriented experiments

### Motivation
A track can feel thin or compressed without lacking sub-bass in a literal bandwidth sense.

### Possible directions

- controlled subharmonic enhancement;
- bass-oriented AI post-processing;
- stem separation followed by focused low-end treatment;
- drum / bass specific restoration chains.

### Caution
This area may move from **restoration** toward **creative remastering**. The application should make that distinction explicit.

---

# Data and evaluation roadmap

## 🚧 V7 — Ground-truth evaluation bench

### Goal
Create a small scientific benchmark using genuinely high-quality reference files.

### Proposed workflow

```text
Lossless master
→ controlled degradation / codec compression
→ restoration model
→ compare restored result with original lossless master
````

### Planned metrics

* full-reference spectral distances;
* high-frequency reconstruction fidelity;
* perceptual metrics where relevant;
* subjective A/B notes.

### Why it matters

Without a ground truth, a model can only be judged by plausibility. With a real reference, we can begin to ask:

> Did the model recover something actually closer to the lost original?

---

# UI / UX roadmap

## 🚧 V8 — Richer project navigation

### Planned

* Project list sidebar
* Resume previous projects
* Render history by project
* Analysis history by render
* Delete / archive generated runs
* Search by track title / source

---

## 🚧 V8.1 — Better diagnostics dashboard

### Planned

* Project overview cards
* Render comparison tables
* Quick warning badges
* “Most altered bands” summaries
* “Possible treble shift” indicators
* “Residual mostly HF” indicators

---

# Engineering roadmap

## 🚧 V9 — Reproducible environment and packaging

### Planned

* Create `environment.yml`
* Add dependency version notes
* Add setup documentation for Windows
* Consider optional non-GPU mode detection
* Improve runtime dependency checks
* Improve startup diagnostics
* Package a distributable Windows build when feasible

---

## 🚧 V9.1 — Logging and resilience

### Planned

* Persistent application logs
* Better exception surfacing in UI
* Cancel jobs / stop processing
* Recover partially completed jobs
* Safer temp folder handling
* Disk space checks before long jobs

---

# Suggested next development priority

The most valuable immediate work is:

1. **show analysis graphs inside the UI**;
2. **add synchronized A/B listening**;
3. **introduce interpretation labels for the existing metrics**.

These three steps will make the app far more useful before adding new restoration engines.
