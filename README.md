# audio-upscale-lab
Local desktop lab for downloading, AI upscaling and analyzing audio sources.

# `README.md`

````markdown
# Audio Upscale Lab

**Audio Upscale Lab** is a local desktop application for experimenting with AI-based audio restoration and measuring what these models actually change.

The current pipeline can:

1. download the best available audio stream from a YouTube URL;
2. archive the original source locally;
3. generate a clean **48 kHz / 24-bit PCM WAV** reference file;
4. upscale that reference with **AudioSR**;
5. compare the original and the processed version through a detailed analysis report:
   - global loudness and RMS deltas;
   - spectral centroid and rolloff changes;
   - energy distribution by frequency band;
   - high-frequency enrichment metrics;
   - residual analysis (`processed - original`);
   - spectrograms, residual spectrograms, and temporal difference plots;
   - difference WAV files for critical listening.

The project is intentionally designed as a **laboratory**, not as a one-click “make audio better” tool. Its purpose is to understand when AI audio upscaling genuinely enriches a compressed source, and when it merely shifts the tonal balance or introduces artificial brilliance.

---

## Current status

The project is already usable as a first local prototype.

### Implemented

- Desktop interface with **PyWebView**
- YouTube audio download pipeline with `yt-dlp`
- Automatic source archiving and project folder creation
- 48 kHz / 24-bit WAV reference generation with `ffmpeg`
- AudioSR upscale pipeline integrated into the GUI
- Background job execution with progress tracking and logs
- Comparative analysis pipeline integrated into the GUI
- Generation of:
  - analysis reports in JSON;
  - CSV summary tables;
  - diagnostic graphs in PNG;
  - full residual WAV;
  - high-frequency residual WAV.

### Not yet implemented

- Interactive display of the generated graphs directly inside the app
- Integrated A/B synchronized listening player
- Multiple upscale profiles and ranking views
- Quality / plausibility scoring for upscales
- Alternative restoration engines beyond AudioSR
- Build / packaging workflow for end users

---

## Why this project exists

A common temptation is to convert a compressed source to FLAC or WAV and assume that a larger file means better sound. It does not. A lossy source stays lossy.

AI restoration tools, however, open a more interesting question:

> Can a model reconstruct plausible audio information from a compressed source — and can we measure whether that reconstruction is musically useful?

**Audio Upscale Lab** explores that question.

The project arose from hands-on testing of AudioSR on YouTube-derived audio. Early tests showed that:

- AudioSR can genuinely add high-frequency content;
- this content is not always naturally audible without careful A/B comparison;
- the model may shift the spectral centre of gravity toward the treble;
- the result can feel brighter or sharper without necessarily sounding deeper or more expansive.

This motivated a workflow that combines:

- **listening**;
- **objective analysis**;
- **reproducible settings**;
- **traceable project outputs**.

---

## High-level workflow

```text
YouTube URL
   ↓
yt-dlp downloads the best available audio stream
   ↓
Original source archived locally (`source.webm`, etc.)
   ↓
FFmpeg creates a 48 kHz / 24-bit WAV reference
   ↓
AudioSR generates an upscaled WAV
   ↓
Analysis engine compares reference vs processed output
   ↓
Reports, tables, graphs and difference WAVs are generated
````

---

## Project folder structure

```text
AUDIO UPSCALE LAB/
├── app.py
├── run_app.bat
├── backend/
│   ├── __init__.py
│   ├── api.py
│   ├── pipeline.py
│   ├── audiosr_runner.py
│   └── audio_analysis_runner.py
├── ui/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── workspace/
    └── projects/
        └── <project-key>/
            ├── project.json
            ├── source/
            ├── prepared/
            ├── upscale/
            └── analysis/
```

Generated projects are intentionally ignored by Git.

---

## Generated project structure

A project created from a source URL typically looks like this:

```text
workspace/projects/<project-key>/
├── project.json
├── source/
│   └── source.webm
├── prepared/
│   └── reference_48k_pcm24.wav
├── upscale/
│   └── audiosr_<timestamp>_<id>/
│       └── audiosr_upscaled_48k_pcm24.wav
└── analysis/
    └── comparison_<timestamp>_<id>/
        ├── analysis_report.json
        ├── band_energy_table.csv
        ├── high_frequency_summary.csv
        ├── residual_band_energy_table.csv
        ├── residual_high_frequency_summary.csv
        ├── difference_full_processed_minus_original.wav
        ├── difference_highfreq_8k_23k5.wav
        └── *.png
```

---

## Analysis outputs

The analysis pipeline currently produces several families of diagnostics.

### Global audio metrics

* duration and alignment checks;
* peak level;
* RMS level;
* integrated loudness;
* stereo correlation;
* mid / side balance;
* spectral centroid;
* 95% spectral rolloff;
* spectral flatness.

### Band-based analysis

Frequency bands currently monitored:

* 20–80 Hz
* 80–250 Hz
* 250–1000 Hz
* 1–4 kHz
* 4–8 kHz
* 8–12 kHz
* 12–16 kHz
* 16–20 kHz
* 20–24 kHz

For each band, the tool estimates:

* original power;
* processed power;
* delta in dB;
* share of total power before / after;
* contribution to the residual.

### High-frequency summary

Dedicated summaries are generated for:

* ≥ 8 kHz
* ≥ 12 kHz
* ≥ 16 kHz
* ≥ 20 kHz

This is particularly useful with AudioSR, which often acts primarily as a high-frequency reconstruction engine.

### Residual analysis

The residual is defined as:

```text
processed signal − original signal
```

The app exports:

* a **full residual WAV**;
* a **high-frequency residual WAV** filtered between approximately 8 kHz and 23.5 kHz.

These files make it possible to listen directly to what the processing changed or generated.

---

## Current interpretation philosophy

The app does **not** currently claim that “more reconstructed frequency content” means “better audio”.

Instead, it tries to separate several questions:

1. **Did the algorithm meaningfully change the audio?**
2. **Where did it change it?**
3. **Did it mostly add information in the upper spectrum?**
4. **Did it alter the balance of the original master?**
5. **Does the residual look like structured musical detail or like diffuse artificial texture?**

This distinction matters. A model can produce a technically impressive spectral extension while still sounding slightly over-bright or aesthetically unconvincing.

---

## Tech stack

### Desktop UI

* Python
* PyWebView
* HTML / CSS / JavaScript

### Download and preparation

* `yt-dlp`
* `Deno` / EJS support for robust YouTube extraction
* `ffmpeg`
* `ffprobe`

### AI processing

* AudioSR
* PyTorch + CUDA

### Analysis

* NumPy
* SciPy
* Librosa
* SoundFile
* pyloudnorm
* Matplotlib

---

## Development environment

The project is currently developed on Windows with a Conda environment.

A future task is to provide a clean, pinned `environment.yml` and a proper packaging path.

### Current known working GPU stack

The AudioSR integration has been tested with:

```text
PyTorch 2.0.1 + CUDA 11.8
CUDA available: True
```

---

## Local setup — current manual path

> This section documents the current development workflow. It will be refined as the project becomes easier to install.

### 1. Clone the repository

```bash
git clone https://github.com/kxsb/audio-upscale-lab.git
cd audio-upscale-lab
```

### 2. Create a Conda environment

Example:

```bash
conda create -n audio-upscale-lab python=3.10 -y
conda activate audio-upscale-lab
```

### 3. Install core app dependencies

```bash
pip install pywebview "yt-dlp[default]"
```

### 4. Install PyTorch CUDA stack

```bash
pip install \
  --extra-index-url https://download.pytorch.org/whl/cu118 \
  torch==2.0.1+cu118 \
  torchvision==0.15.2+cu118 \
  torchaudio==2.0.2+cu118
```

### 5. Install AudioSR and analysis dependencies

```bash
pip install \
  "git+https://github.com/huggingface/diffusers.git" \
  "transformers==4.30.2" \
  "audiosr==0.0.7" \
  soundfile \
  progressbar \
  librosa \
  matplotlib \
  unidecode \
  scipy \
  pyloudnorm \
  cog \
  soxr
```

### 6. Keep Setuptools compatible with older Librosa / AudioSR internals

```bash
pip install "setuptools<81"
```

### 7. Install external tools

The app expects the following executables to be available in the system `PATH`:

* `ffmpeg`
* `ffprobe`
* `deno`

### 8. Launch the app

On Windows:

```text
run_app.bat
```

---

## Current limitations

* The app currently targets a local Windows-based development setup.
* The generated analysis graphs are produced in project folders but are not yet browsable inside the UI.
* AudioSR is currently the only AI processing engine integrated.
* The GUI does not yet include an A/B audio player.
* No global “quality score” is implemented yet.
* Long AudioSR jobs can be slow and GPU-memory intensive.
* The current app is a research prototype, not a packaged end-user release.

---

## What would make this project genuinely powerful

The long-term direction is not merely “AI upscale”. It is:

> **A local audio restoration lab that can run multiple processing engines, compare their effects, and help decide whether the result is musically better or only spectrally more impressive.**

Potential future areas include:

* interactive graph exploration with Plotly.js;
* synchronized A/B listening;
* render comparison dashboards;
* multiple AI engines;
* global enrichment / low-frequency enhancement experiments;
* quality-plausibility scoring;
* user preference learning over repeated A/B judgments.

---

## Repository

GitHub: `https://github.com/kxsb/audio-upscale-lab`

---

## License

No license has been selected yet.

````

---

# `ROADMAP.md`

```markdown
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

---

# Long-term vision

> **Audio Upscale Lab should become a local, transparent and critical workspace for AI-assisted audio restoration — a tool that does not merely promise “better sound”, but shows what changed, lets the listener hear it, and helps judge whether the change was worth it
