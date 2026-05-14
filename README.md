# audio-upscale-lab
Local desktop lab for downloading, AI upscaling and analyzing audio sources.

# `README.md`

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

---

# Long-term vision

> **Audio Upscale Lab should become a local, transparent and critical workspace for AI-assisted audio restoration — a tool that does not merely promise “better sound”, but shows what changed, lets the listener hear it, and helps judge whether the change was worth it
