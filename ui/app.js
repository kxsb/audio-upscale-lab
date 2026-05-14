let currentProject = null;

// AudioSR
let currentAudiosrJobId = null;
let currentAudiosrRunDir = null;
let currentAudiosrOutputWav = null;
let currentAudiosrSettings = null;
let audiosrPollTimer = null;

// Analyse
let currentAnalysisJobId = null;
let currentAnalysisRunDir = null;
let analysisPollTimer = null;

const $ = (id) => document.getElementById(id);


// ============================================================
// OUTILS GÉNÉRAUX
// ============================================================

function appendLog(message) {
  const output = $("logOutput");

  if (output.textContent === "En attente...") {
    output.textContent = "";
  }

  output.textContent += `${message}\n`;
  output.scrollTop = output.scrollHeight;
}


function resetLog() {
  $("logOutput").textContent = "";
}


function setStatus(kind, title, message) {
  const card = $("statusCard");
  const dot = card.querySelector(".status-dot");

  $("statusTitle").textContent = title;
  $("statusMessage").textContent = message;

  if (kind === "error") {
    dot.style.background = "var(--danger)";
    dot.style.boxShadow = "0 0 0 8px rgba(239, 68, 68, 0.14)";
    return;
  }

  if (kind === "busy") {
    dot.style.background = "var(--warning)";
    dot.style.boxShadow = "0 0 0 8px rgba(245, 158, 11, 0.14)";
    return;
  }

  dot.style.background = "var(--success)";
  dot.style.boxShadow = "0 0 0 8px rgba(34, 197, 94, 0.14)";
}


function chip(label, ok, detail = "") {
  const className = ok ? "chip chip-ok" : "chip chip-warn";
  const suffix = detail ? ` · ${detail}` : "";

  return `<span class="${className}">${label}${suffix}</span>`;
}


function renderDependencies(dependencies) {
  const strip = $("dependencyStrip");

  const yt = dependencies.yt_dlp;
  const ejs = dependencies.yt_dlp_ejs;
  const deno = dependencies.deno;
  const ffmpeg = dependencies.ffmpeg;
  const ffprobe = dependencies.ffprobe;

  strip.innerHTML = [
    chip("yt-dlp", yt.available, yt.version || ""),
    chip("EJS", ejs.available),
    chip("Deno", deno.available),
    chip("FFmpeg", ffmpeg.available),
    chip("FFprobe", ffprobe.available),
  ].join("");
}


function pickAudioStream(probe) {
  if (!probe || !Array.isArray(probe.streams)) {
    return null;
  }

  return probe.streams.find((stream) => stream.codec_type === "audio") || null;
}


function formatProbe(probe) {
  const stream = pickAudioStream(probe);
  const format = probe?.format || {};

  if (!stream) {
    return "Informations techniques indisponibles.";
  }

  const codec = stream.codec_name || "codec ?";
  const sampleRate = stream.sample_rate ? `${stream.sample_rate} Hz` : "SR ?";
  const channels = stream.channels ? `${stream.channels} canaux` : "canaux ?";
  const duration = format.duration
    ? `${Number(format.duration).toFixed(2)} s`
    : "durée ?";

  return `${codec} · ${sampleRate} · ${channels} · ${duration}`;
}


function fileNameFromPath(path) {
  return path.split(/[\\/]/).pop();
}


function formatSigned(value, digits = 2, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }

  const number = Number(value);
  const sign = number > 0 ? "+" : "";

  return `${sign}${number.toFixed(digits)}${suffix}`;
}


function formatPlain(value, digits = 2, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }

  return `${Number(value).toFixed(digits)}${suffix}`;
}


function setBusy(isBusy) {
  const button = $("prepareButton");

  button.disabled = isBusy;
  $("prepareButtonLabel").textContent = isBusy
    ? "Préparation..."
    : "Préparer la source";
}


// ============================================================
// PROJET SOURCE
// ============================================================

function renderProject(project) {
  currentProject = project;

  $("emptyResult").classList.add("hidden");
  $("projectResult").classList.remove("hidden");
  $("upscalePanel").classList.remove("hidden");

  const metadata = project.metadata;
  const paths = project.paths;
  const technical = project.technical_info;

  $("projectTitle").textContent = metadata.title;
  $("projectMeta").textContent =
    `${metadata.uploader || "Chaîne inconnue"} · ID ${metadata.id}`;

  $("sourceFileName").textContent = fileNameFromPath(paths.source_file);
  $("sourceTechnical").textContent = formatProbe(technical.source_probe);

  $("referenceFileName").textContent = fileNameFromPath(paths.reference_wav);
  $("referenceTechnical").textContent = formatProbe(technical.reference_probe);

  resetAudiosrPanel();
  resetAnalysisPanel();
}


async function boot() {
  try {
    const ping = await window.pywebview.api.ping();

    if (ping.ok) {
      setStatus("ready", "Prêt", "Le pont Python est opérationnel.");
    }

    const depResponse = await window.pywebview.api.check_dependencies();

    if (depResponse.ok) {
      renderDependencies(depResponse.dependencies);
    } else {
      appendLog(depResponse.error || "Erreur de vérification des dépendances.");
      setStatus(
        "error",
        "Dépendances incertaines",
        depResponse.error || "Erreur."
      );
    }
  } catch (error) {
    setStatus("error", "Pont Python indisponible", String(error));
    appendLog(String(error));
  }
}


async function prepareSource() {
  const url = $("youtubeUrl").value.trim();

  if (!url) {
    setStatus("error", "URL manquante", "Colle une URL YouTube.");
    return;
  }

  resetLog();
  setBusy(true);
  setStatus(
    "busy",
    "Pipeline en cours",
    "Téléchargement et préparation de la source..."
  );
  appendLog("Démarrage du pipeline.");

  try {
    const response = await window.pywebview.api.prepare_youtube_source(url);

    if (!response.ok) {
      setStatus("error", "Échec du pipeline", response.error || "Erreur inconnue.");
      appendLog(response.error || "Erreur inconnue.");
      return;
    }

    for (const line of response.logs || []) {
      appendLog(line);
    }

    renderProject(response.project);
    setStatus("ready", "Source prête", "Le projet local a été créé avec succès.");
  } catch (error) {
    setStatus("error", "Erreur inattendue", String(error));
    appendLog(String(error));
  } finally {
    setBusy(false);
  }
}


async function openProjectFolder() {
  if (!currentProject) {
    return;
  }

  const projectDir = currentProject.paths.project_dir;
  const response = await window.pywebview.api.open_path(projectDir);

  if (!response.ok) {
    setStatus("error", "Ouverture impossible", response.error || "Erreur inconnue.");
  }
}


// ============================================================
// AUDIO SR — ÉTAT UI
// ============================================================

function resetAudiosrPanel() {
  currentAudiosrJobId = null;
  currentAudiosrRunDir = null;
  currentAudiosrOutputWav = null;
  currentAudiosrSettings = null;

  if (audiosrPollTimer) {
    clearInterval(audiosrPollTimer);
    audiosrPollTimer = null;
  }

  $("audiosrJobTitle").textContent = "Aucun job AudioSR lancé";
  $("audiosrJobMessage").textContent =
    "Le traitement apparaîtra ici avec sa progression.";
  $("audiosrJobPercent").textContent = "0%";
  $("audiosrProgressBar").style.width = "0%";

  $("audiosrLogOutput").textContent = "En attente d’un traitement...";
  $("audiosrResult").classList.add("hidden");
  $("openUpscaleFolderButton").classList.add("hidden");

  setAudiosrBusy(false);
}


function setAudiosrBusy(isBusy) {
  const button = $("startAudiosrButton");

  button.disabled = isBusy;
  $("startAudiosrButtonLabel").textContent = isBusy
    ? "AudioSR en cours..."
    : "Lancer l’upscale AudioSR";
}


function collectAudiosrSettings() {
  return {
    model_name: "basic",
    device: "cuda:0",
    guidance_scale: Number($("audiosrGuidanceScale").value),
    input_cutoff: Number($("audiosrInputCutoff").value),
    ddim_steps: Number($("audiosrDdimSteps").value),
    seed: Number($("audiosrSeed").value),
    chunk_size: Number($("audiosrChunkSize").value),
    overlap: Number($("audiosrOverlap").value),
    multiband_ensemble: $("audiosrMultiband").checked,
  };
}


function renderAudiosrLogs(logs) {
  const output = $("audiosrLogOutput");

  if (!logs || logs.length === 0) {
    output.textContent = "Aucun log pour l’instant.";
    return;
  }

  output.textContent = logs.join("\n");
  output.scrollTop = output.scrollHeight;
}


function renderAudiosrProgress(job) {
  const progress = job.progress || {};
  const done = progress.done || 0;
  const total = progress.total || 0;
  const percent = Number(progress.percent || 0);

  $("audiosrJobPercent").textContent = `${percent.toFixed(0)}%`;
  $("audiosrProgressBar").style.width = `${Math.min(percent, 100)}%`;

  if (job.status === "queued") {
    $("audiosrJobTitle").textContent = "Job AudioSR en file";
    $("audiosrJobMessage").textContent =
      "Le traitement va démarrer.";
    return;
  }

  if (job.status === "running") {
    $("audiosrJobTitle").textContent = "Traitement AudioSR en cours";

    if (total > 0) {
      $("audiosrJobMessage").textContent =
        `${done}/${total} chunks traités.`;
    } else {
      $("audiosrJobMessage").textContent =
        "Préparation du modèle et du fichier audio...";
    }

    return;
  }

  if (job.status === "done") {
    $("audiosrJobTitle").textContent = "Upscale AudioSR terminé";
    $("audiosrJobMessage").textContent =
      "Le fichier upscalé est prêt.";
    $("audiosrJobPercent").textContent = "100%";
    $("audiosrProgressBar").style.width = "100%";
    return;
  }

  if (job.status === "error") {
    $("audiosrJobTitle").textContent = "Échec du traitement AudioSR";
    $("audiosrJobMessage").textContent =
      job.error || "Une erreur est survenue.";
  }
}


function renderAudiosrResult(job) {
  if (!job.result) {
    return;
  }

  const outputWav = job.result.output_wav;
  const outputProbe = job.result.output_probe;

  $("audiosrResult").classList.remove("hidden");
  $("audiosrOutputFileName").textContent = fileNameFromPath(outputWav);
  $("audiosrOutputTechnical").textContent = formatProbe(outputProbe);

  currentAudiosrRunDir = job.run_dir;
  currentAudiosrOutputWav = outputWav;
  currentAudiosrSettings = job.settings;

  $("openUpscaleFolderButton").classList.remove("hidden");

  // Une fois l'upscale terminé, on peut analyser ce rendu.
  resetAnalysisPanel();
  $("analysisPanel").classList.remove("hidden");
}


// ============================================================
// AUDIO SR — ACTIONS
// ============================================================

async function startAudiosrUpscale() {
  if (!currentProject) {
    setStatus(
      "error",
      "Aucun projet courant",
      "Prépare d’abord une source YouTube."
    );
    return;
  }

  if (currentAudiosrJobId) {
    setStatus(
      "error",
      "Job déjà actif",
      "Un traitement AudioSR est déjà suivi par l’interface."
    );
    return;
  }

  const settings = collectAudiosrSettings();

  setAudiosrBusy(true);
  $("audiosrResult").classList.add("hidden");
  $("openUpscaleFolderButton").classList.add("hidden");
  $("analysisPanel").classList.add("hidden");

  $("audiosrLogOutput").textContent = "Création du job AudioSR...";
  $("audiosrJobTitle").textContent = "Création du job...";
  $("audiosrJobMessage").textContent = "Initialisation.";
  $("audiosrJobPercent").textContent = "0%";
  $("audiosrProgressBar").style.width = "0%";

  try {
    const response = await window.pywebview.api.start_audiosr_upscale(
      currentProject.project_key,
      settings
    );

    if (!response.ok) {
      setAudiosrBusy(false);
      setStatus(
        "error",
        "Impossible de lancer AudioSR",
        response.error || "Erreur inconnue."
      );
      $("audiosrLogOutput").textContent =
        response.error || "Erreur inconnue.";
      return;
    }

    currentAudiosrJobId = response.job_id;

    renderAudiosrProgress(response.job);
    renderAudiosrLogs(response.job.logs);

    setStatus(
      "busy",
      "AudioSR lancé",
      "Le traitement tourne en arrière-plan."
    );

    audiosrPollTimer = setInterval(pollAudiosrJob, 1000);
  } catch (error) {
    setAudiosrBusy(false);
    setStatus(
      "error",
      "Erreur de lancement AudioSR",
      String(error)
    );
    $("audiosrLogOutput").textContent = String(error);
  }
}


async function pollAudiosrJob() {
  if (!currentAudiosrJobId) {
    return;
  }

  try {
    const response = await window.pywebview.api.get_job_status(
      currentAudiosrJobId
    );

    if (!response.ok) {
      setStatus(
        "error",
        "Suivi de job perdu",
        response.error || "Erreur inconnue."
      );

      stopAudiosrPolling();
      setAudiosrBusy(false);
      return;
    }

    const job = response.job;

    renderAudiosrProgress(job);
    renderAudiosrLogs(job.logs);

    if (job.status === "done") {
      renderAudiosrResult(job);
      setStatus(
        "ready",
        "AudioSR terminé",
        "Le fichier upscalé a été généré."
      );
      stopAudiosrPolling();
      setAudiosrBusy(false);
      currentAudiosrJobId = null;
      return;
    }

    if (job.status === "error") {
      setStatus(
        "error",
        "AudioSR en erreur",
        job.error || "Le traitement a échoué."
      );
      stopAudiosrPolling();
      setAudiosrBusy(false);
      currentAudiosrJobId = null;
    }
  } catch (error) {
    setStatus(
      "error",
      "Erreur pendant le suivi AudioSR",
      String(error)
    );
    stopAudiosrPolling();
    setAudiosrBusy(false);
    currentAudiosrJobId = null;
  }
}


function stopAudiosrPolling() {
  if (audiosrPollTimer) {
    clearInterval(audiosrPollTimer);
    audiosrPollTimer = null;
  }
}


async function openUpscaleFolder() {
  if (!currentAudiosrRunDir) {
    return;
  }

  const response = await window.pywebview.api.open_path(
    currentAudiosrRunDir
  );

  if (!response.ok) {
    setStatus(
      "error",
      "Ouverture impossible",
      response.error || "Erreur inconnue."
    );
  }
}


// ============================================================
// ANALYSE — ÉTAT UI
// ============================================================

function resetAnalysisPanel() {
  currentAnalysisJobId = null;
  currentAnalysisRunDir = null;

  if (analysisPollTimer) {
    clearInterval(analysisPollTimer);
    analysisPollTimer = null;
  }

  $("analysisJobTitle").textContent = "Aucune analyse lancée";
  $("analysisJobMessage").textContent =
    "Le rapport comparatif apparaîtra ici avec sa progression.";
  $("analysisJobPercent").textContent = "0%";
  $("analysisProgressBar").style.width = "0%";

  $("analysisLogOutput").textContent = "En attente d’une analyse...";
  $("analysisResult").classList.add("hidden");
  $("openAnalysisFolderButton").classList.add("hidden");

  $("analysisResidualPct").textContent = "—";
  $("analysisResidualDb").textContent = "—";
  $("analysisCentroidDelta").textContent = "—";
  $("analysisRolloffDelta").textContent = "—";

  $("analysisHighFrequencyRows").innerHTML = `
    <tr>
      <td colspan="5">En attente d’analyse.</td>
    </tr>
  `;

  setAnalysisBusy(false);
}


function setAnalysisBusy(isBusy) {
  const button = $("startAnalysisButton");

  button.disabled = isBusy;
  $("startAnalysisButtonLabel").textContent = isBusy
    ? "Analyse en cours..."
    : "Analyser ce rendu";
}


function renderAnalysisLogs(logs) {
  const output = $("analysisLogOutput");

  if (!logs || logs.length === 0) {
    output.textContent = "Aucun log pour l’instant.";
    return;
  }

  output.textContent = logs.join("\n");
  output.scrollTop = output.scrollHeight;
}


function renderAnalysisProgress(job) {
  const progress = job.progress || {};
  const done = progress.done || 0;
  const total = progress.total || 0;
  const percent = Number(progress.percent || 0);

  $("analysisJobPercent").textContent = `${percent.toFixed(0)}%`;
  $("analysisProgressBar").style.width = `${Math.min(percent, 100)}%`;

  if (job.status === "queued") {
    $("analysisJobTitle").textContent = "Analyse en file";
    $("analysisJobMessage").textContent =
      "Le moteur d’analyse va démarrer.";
    return;
  }

  if (job.status === "running") {
    $("analysisJobTitle").textContent = "Analyse comparative en cours";

    if (total > 0) {
      $("analysisJobMessage").textContent =
        `${done}/${total} étapes réalisées.`;
    } else {
      $("analysisJobMessage").textContent =
        "Préparation de l’analyse...";
    }

    return;
  }

  if (job.status === "done") {
    $("analysisJobTitle").textContent = "Analyse comparative terminée";
    $("analysisJobMessage").textContent =
      "Le rapport, les graphes et les fichiers de différence sont prêts.";
    $("analysisJobPercent").textContent = "100%";
    $("analysisProgressBar").style.width = "100%";
    return;
  }

  if (job.status === "error") {
    $("analysisJobTitle").textContent = "Échec de l’analyse comparative";
    $("analysisJobMessage").textContent =
      job.error || "Une erreur est survenue.";
  }
}


function buildAnalysisLabel() {
  const settings = currentAudiosrSettings || {};
  const guidance = settings.guidance_scale ?? "?";
  const cutoff = settings.input_cutoff ?? "?";
  const multiband = settings.multiband_ensemble ? "multiband" : "full";

  return `AudioSR basic · guidance ${guidance} · cutoff ${cutoff} Hz · ${multiband}`;
}


function collectAnalysisContext() {
  const settings = currentAudiosrSettings || {};

  return {
    label: buildAnalysisLabel(),
    chunk_size_s: settings.chunk_size ?? null,
    chunk_overlap_fraction: settings.overlap ?? null,
  };
}


function metricClassForSignedValue(value) {
  const numeric = Number(value);

  if (!Number.isFinite(numeric)) {
    return "metric-neutral";
  }

  if (numeric > 0) {
    return "metric-warning";
  }

  return "metric-neutral";
}


function renderHighFrequencyTable(rows) {
  const tbody = $("analysisHighFrequencyRows");

  if (!rows || rows.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5">Aucune synthèse haute fréquence disponible.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = rows.map((row) => {
    const deltaShare = Number(row.delta_share_pp);
    const deltaPower = Number(row.delta_power_db);

    return `
      <tr>
        <td>${row.range}</td>
        <td>${formatPlain(row.original_share_pct, 5, " %")}</td>
        <td>${formatPlain(row.processed_share_pct, 5, " %")}</td>
        <td class="${metricClassForSignedValue(deltaShare)}">
          ${formatSigned(deltaShare, 5, " pts")}
        </td>
        <td class="${metricClassForSignedValue(deltaPower)}">
          ${formatSigned(deltaPower, 2, " dB")}
        </td>
      </tr>
    `;
  }).join("");
}


function renderAnalysisResult(job) {
  if (!job.result || !job.result.summary) {
    return;
  }

  const summary = job.result.summary;
  const metrics = summary.metrics || {};

  $("analysisResult").classList.remove("hidden");
  $("openAnalysisFolderButton").classList.remove("hidden");

  $("analysisResidualPct").textContent =
    formatPlain(metrics.residual_rms_pct_of_original_rms, 2, " %");

  $("analysisResidualDb").textContent =
    formatSigned(metrics.residual_rms_vs_original_db, 2, " dB");

  $("analysisCentroidDelta").textContent =
    formatSigned(metrics.spectral_centroid_delta_hz, 0, " Hz");

  $("analysisRolloffDelta").textContent =
    formatSigned(metrics.spectral_rolloff_95_delta_hz, 0, " Hz");

  renderHighFrequencyTable(summary.high_frequency_summary);

  currentAnalysisRunDir = summary.output_dir;
}


// ============================================================
// ANALYSE — ACTIONS
// ============================================================

async function startAudioAnalysis() {
  if (!currentProject) {
    setStatus(
      "error",
      "Aucun projet courant",
      "Prépare d’abord une source YouTube."
    );
    return;
  }

  if (!currentAudiosrOutputWav) {
    setStatus(
      "error",
      "Aucun rendu à analyser",
      "Lance d’abord un upscale AudioSR."
    );
    return;
  }

  if (currentAnalysisJobId) {
    setStatus(
      "error",
      "Analyse déjà active",
      "Une analyse comparative est déjà suivie par l’interface."
    );
    return;
  }

  setAnalysisBusy(true);
  $("analysisResult").classList.add("hidden");
  $("openAnalysisFolderButton").classList.add("hidden");

  $("analysisLogOutput").textContent = "Création du job d’analyse...";
  $("analysisJobTitle").textContent = "Création du job...";
  $("analysisJobMessage").textContent = "Initialisation.";
  $("analysisJobPercent").textContent = "0%";
  $("analysisProgressBar").style.width = "0%";

  try {
    const response = await window.pywebview.api.start_audio_analysis(
      currentProject.project_key,
      currentAudiosrOutputWav,
      collectAnalysisContext()
    );

    if (!response.ok) {
      setAnalysisBusy(false);
      setStatus(
        "error",
        "Impossible de lancer l’analyse",
        response.error || "Erreur inconnue."
      );
      $("analysisLogOutput").textContent =
        response.error || "Erreur inconnue.";
      return;
    }

    currentAnalysisJobId = response.job_id;

    renderAnalysisProgress(response.job);
    renderAnalysisLogs(response.job.logs);

    setStatus(
      "busy",
      "Analyse lancée",
      "Le rapport comparatif est en cours de génération."
    );

    analysisPollTimer = setInterval(pollAnalysisJob, 1000);
  } catch (error) {
    setAnalysisBusy(false);
    setStatus(
      "error",
      "Erreur de lancement de l’analyse",
      String(error)
    );
    $("analysisLogOutput").textContent = String(error);
  }
}


async function pollAnalysisJob() {
  if (!currentAnalysisJobId) {
    return;
  }

  try {
    const response = await window.pywebview.api.get_job_status(
      currentAnalysisJobId
    );

    if (!response.ok) {
      setStatus(
        "error",
        "Suivi d’analyse perdu",
        response.error || "Erreur inconnue."
      );

      stopAnalysisPolling();
      setAnalysisBusy(false);
      return;
    }

    const job = response.job;

    renderAnalysisProgress(job);
    renderAnalysisLogs(job.logs);

    if (job.status === "done") {
      renderAnalysisResult(job);
      setStatus(
        "ready",
        "Analyse terminée",
        "Le rapport comparatif est disponible."
      );
      stopAnalysisPolling();
      setAnalysisBusy(false);
      currentAnalysisJobId = null;
      return;
    }

    if (job.status === "error") {
      setStatus(
        "error",
        "Analyse en erreur",
        job.error || "Le traitement a échoué."
      );
      stopAnalysisPolling();
      setAnalysisBusy(false);
      currentAnalysisJobId = null;
    }
  } catch (error) {
    setStatus(
      "error",
      "Erreur pendant le suivi de l’analyse",
      String(error)
    );
    stopAnalysisPolling();
    setAnalysisBusy(false);
    currentAnalysisJobId = null;
  }
}


function stopAnalysisPolling() {
  if (analysisPollTimer) {
    clearInterval(analysisPollTimer);
    analysisPollTimer = null;
  }
}


async function openAnalysisFolder() {
  if (!currentAnalysisRunDir) {
    return;
  }

  const response = await window.pywebview.api.open_path(
    currentAnalysisRunDir
  );

  if (!response.ok) {
    setStatus(
      "error",
      "Ouverture impossible",
      response.error || "Erreur inconnue."
    );
  }
}


// ============================================================
// ÉVÉNEMENTS
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  $("prepareButton").addEventListener("click", prepareSource);
  $("openProjectButton").addEventListener("click", openProjectFolder);

  $("startAudiosrButton").addEventListener("click", startAudiosrUpscale);
  $("openUpscaleFolderButton").addEventListener("click", openUpscaleFolder);

  $("startAnalysisButton").addEventListener("click", startAudioAnalysis);
  $("openAnalysisFolderButton").addEventListener("click", openAnalysisFolder);

  $("youtubeUrl").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      prepareSource();
    }
  });
});


window.addEventListener("pywebviewready", boot);