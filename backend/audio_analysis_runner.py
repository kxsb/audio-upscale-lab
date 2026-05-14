from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import librosa
import librosa.display

import matplotlib

# Backend non interactif : indispensable depuis une app desktop.
matplotlib.use("Agg")

import matplotlib.pyplot as plt

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy import signal



LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]


# ============================================================
# CONSTANTES
# ============================================================

TARGET_SR = 48000
ALIGNMENT_SR = 4000
MAX_ALIGN_LAG_S = 0.50

EPSILON = 1e-20
DB_FLOOR = -120.0

BANDS_HZ: list[tuple[int, int]] = [
    (20, 80),
    (80, 250),
    (250, 1000),
    (1000, 4000),
    (4000, 8000),
    (8000, 12000),
    (12000, 16000),
    (16000, 20000),
    (20000, 24000),
]

HIGH_FREQ_THRESHOLDS = [8000, 12000, 16000, 20000]

STFT_N_FFT = 4096
STFT_HOP = 1024


# ============================================================
# DATACLASSES
# ============================================================

@dataclass
class SourceDiagnostics:
    path: str
    samplerate_hz: int
    channels: int
    frames: int
    duration_s: float
    format: str
    subtype: str
    subtype_info: str
    peak_dbfs_raw_decode: float
    rms_dbfs_raw_decode: float
    max_abs_raw_decode: float
    near_full_scale_samples_abs_ge_0_999: int
    near_full_scale_share_pct: float
    above_full_scale_samples_abs_gt_1_0: int


@dataclass
class AudioPair:
    original: np.ndarray
    processed: np.ndarray
    sample_rate: int
    alignment_lag_samples: int
    alignment_lag_ms: float
    original_path: Path
    processed_path: Path


# ============================================================
# OUTILS MATHS / NIVEAUX
# ============================================================

def safe_log10(value: float) -> float:
    return math.log10(max(float(value), EPSILON))


def power_to_db(power: float) -> float:
    return 10.0 * safe_log10(power)


def amplitude_to_db(amplitude: float) -> float:
    return 20.0 * safe_log10(amplitude)


def db_ratio(numerator_power: float, denominator_power: float) -> float:
    return 10.0 * safe_log10(numerator_power / max(denominator_power, EPSILON))


def rms_linear(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))


def peak_dbfs(audio: np.ndarray) -> float:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    return amplitude_to_db(peak)


def rms_dbfs(audio: np.ndarray) -> float:
    return amplitude_to_db(rms_linear(audio))


def ensure_2d(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio[:, None]
    return audio


def ensure_stereo_for_display(audio: np.ndarray) -> np.ndarray:
    """
    Garde les analyses compatibles mono/stéréo.
    Les calculs spectraux se font de toute façon sur un mix mono.
    """
    audio = ensure_2d(audio)

    if audio.shape[1] == 1:
        return np.repeat(audio, 2, axis=1)

    return audio


def mono_mix(audio: np.ndarray) -> np.ndarray:
    audio = ensure_2d(audio)
    return np.mean(audio, axis=1)


def integrated_lufs(audio: np.ndarray, sr: int) -> float:
    try:
        meter = pyln.Meter(sr)
        audio_2d = ensure_2d(audio)

        value = meter.integrated_loudness(audio_2d)

        if np.isfinite(value):
            return float(value)

        return float("nan")
    except Exception:
        return float("nan")


def correlation_lr(audio: np.ndarray) -> float:
    audio = ensure_2d(audio)

    if audio.shape[1] < 2:
        return float("nan")

    left = audio[:, 0]
    right = audio[:, 1]

    if np.std(left) < EPSILON or np.std(right) < EPSILON:
        return float("nan")

    return float(np.corrcoef(left, right)[0, 1])


def mid_side_metrics(audio: np.ndarray) -> dict[str, float]:
    audio = ensure_stereo_for_display(audio)

    left = audio[:, 0]
    right = audio[:, 1]

    mid = (left + right) / 2.0
    side = (left - right) / 2.0

    mid_power = float(np.mean(np.square(mid)))
    side_power = float(np.mean(np.square(side)))
    total = mid_power + side_power

    return {
        "mid_rms_dbfs": rms_dbfs(mid),
        "side_rms_dbfs": rms_dbfs(side),
        "side_share_pct": float((side_power / total) * 100.0) if total > 0 else float("nan"),
    }


# ============================================================
# CHARGEMENT / RESAMPLING / ALIGNEMENT
# ============================================================

def load_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(
        path,
        always_2d=True,
        dtype="float64",
    )

    return audio, int(sr)


def resample_audio(
    audio: np.ndarray,
    original_sr: int,
    target_sr: int,
) -> np.ndarray:
    if original_sr == target_sr:
        return audio

    channels: list[np.ndarray] = []

    for channel_index in range(audio.shape[1]):
        channel = librosa.resample(
            audio[:, channel_index],
            orig_sr=original_sr,
            target_sr=target_sr,
            res_type="soxr_hq",
        )
        channels.append(channel)

    min_len = min(len(channel) for channel in channels)
    channels = [channel[:min_len] for channel in channels]

    return np.stack(channels, axis=1)


def estimate_alignment_lag_samples(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> int:
    """
    Estime le lag processed vs original.

    Convention :
    - lag > 0 : processed est en retard ;
    - lag < 0 : processed est en avance.
    """
    mono_original = mono_mix(original)
    mono_processed = mono_mix(processed)

    # On limite l'alignement sur les 60 premières secondes pour éviter un calcul inutilement massif.
    max_analysis_samples = min(len(mono_original), len(mono_processed), sr * 60)

    mono_original = mono_original[:max_analysis_samples]
    mono_processed = mono_processed[:max_analysis_samples]

    original_low = librosa.resample(
        mono_original,
        orig_sr=sr,
        target_sr=ALIGNMENT_SR,
        res_type="soxr_hq",
    )

    processed_low = librosa.resample(
        mono_processed,
        orig_sr=sr,
        target_sr=ALIGNMENT_SR,
        res_type="soxr_hq",
    )

    original_low = original_low - np.mean(original_low)
    processed_low = processed_low - np.mean(processed_low)

    max_lag_low_sr = int(MAX_ALIGN_LAG_S * ALIGNMENT_SR)

    correlation = signal.correlate(
        processed_low,
        original_low,
        mode="full",
        method="fft",
    )

    lags = signal.correlation_lags(
        len(processed_low),
        len(original_low),
        mode="full",
    )

    valid_mask = np.abs(lags) <= max_lag_low_sr

    correlation_valid = correlation[valid_mask]
    lags_valid = lags[valid_mask]

    best_lag_low_sr = int(lags_valid[np.argmax(correlation_valid)])

    lag_samples = int(round(best_lag_low_sr * sr / ALIGNMENT_SR))

    return lag_samples


def align_and_trim_pair(
    original: np.ndarray,
    processed: np.ndarray,
    lag_samples: int,
) -> tuple[np.ndarray, np.ndarray]:
    if lag_samples > 0:
        # processed est en retard : on coupe son début.
        processed = processed[lag_samples:, :]
    elif lag_samples < 0:
        # processed est en avance : on coupe le début de l'original.
        original = original[-lag_samples:, :]

    common_length = min(len(original), len(processed))

    return (
        original[:common_length, :],
        processed[:common_length, :],
    )


def prepare_audio_pair(
    original_path: Path,
    processed_path: Path,
    log: LogCallback,
) -> AudioPair:
    log("Chargement des deux fichiers audio...")

    original, sr_original = load_audio(original_path)
    processed, sr_processed = load_audio(processed_path)

    if sr_original != TARGET_SR:
        log(f"Resampling original : {sr_original} Hz → {TARGET_SR} Hz.")
        original = resample_audio(original, sr_original, TARGET_SR)

    if sr_processed != TARGET_SR:
        log(f"Resampling traité : {sr_processed} Hz → {TARGET_SR} Hz.")
        processed = resample_audio(processed, sr_processed, TARGET_SR)

    original = ensure_2d(original)
    processed = ensure_2d(processed)

    # Harmonisation simple du nombre de canaux.
    if original.shape[1] != processed.shape[1]:
        original = ensure_stereo_for_display(original)
        processed = ensure_stereo_for_display(processed)

    log("Estimation de l’alignement temporel...")

    lag_samples = estimate_alignment_lag_samples(
        original,
        processed,
        TARGET_SR,
    )

    lag_ms = lag_samples / TARGET_SR * 1000.0

    log(f"Lag estimé : {lag_samples} samples / {lag_ms:.3f} ms.")

    original, processed = align_and_trim_pair(
        original,
        processed,
        lag_samples,
    )

    log(
        "Durée commune analysée : "
        f"{len(original) / TARGET_SR:.3f} s."
    )

    return AudioPair(
        original=original,
        processed=processed,
        sample_rate=TARGET_SR,
        alignment_lag_samples=lag_samples,
        alignment_lag_ms=lag_ms,
        original_path=original_path,
        processed_path=processed_path,
    )


# ============================================================
# DIAGNOSTIC FICHIERS SOURCES
# ============================================================

def source_diagnostics(path: Path) -> SourceDiagnostics:
    info = sf.info(path)
    audio, _ = load_audio(path)

    abs_audio = np.abs(audio)
    max_abs = float(np.max(abs_audio)) if audio.size else 0.0

    near_full_scale = int(np.count_nonzero(abs_audio >= 0.999))
    above_full_scale = int(np.count_nonzero(abs_audio > 1.0))
    total_samples = int(audio.size)

    near_full_scale_share = (
        near_full_scale / total_samples * 100.0
        if total_samples > 0
        else 0.0
    )

    return SourceDiagnostics(
        path=str(path),
        samplerate_hz=int(info.samplerate),
        channels=int(info.channels),
        frames=int(info.frames),
        duration_s=float(info.duration),
        format=str(info.format),
        subtype=str(info.subtype),
        subtype_info=str(info.subtype_info),
        peak_dbfs_raw_decode=peak_dbfs(audio),
        rms_dbfs_raw_decode=rms_dbfs(audio),
        max_abs_raw_decode=max_abs,
        near_full_scale_samples_abs_ge_0_999=near_full_scale,
        near_full_scale_share_pct=float(near_full_scale_share),
        above_full_scale_samples_abs_gt_1_0=above_full_scale,
    )


# ============================================================
# SPECTRAL METRICS
# ============================================================

def spectral_metrics(audio: np.ndarray, sr: int) -> dict[str, float]:
    mono = mono_mix(audio).astype(np.float32)

    centroid = librosa.feature.spectral_centroid(
        y=mono,
        sr=sr,
    )

    rolloff = librosa.feature.spectral_rolloff(
        y=mono,
        sr=sr,
        roll_percent=0.95,
    )

    flatness = librosa.feature.spectral_flatness(
        y=mono,
    )

    return {
        "spectral_centroid_hz": float(np.mean(centroid)),
        "spectral_rolloff_95_hz": float(np.mean(rolloff)),
        "spectral_flatness": float(np.mean(flatness)),
    }


def global_metrics(audio: np.ndarray, sr: int) -> dict[str, float | int]:
    duration_s = len(audio) / sr

    metrics: dict[str, float | int] = {
        "sample_rate_hz": int(sr),
        "channels": int(audio.shape[1]),
        "samples": int(len(audio)),
        "duration_s": float(duration_s),
        "peak_dbfs": peak_dbfs(audio),
        "rms_dbfs": rms_dbfs(audio),
        "integrated_lufs": integrated_lufs(audio, sr),
        "lr_correlation": correlation_lr(audio),
    }

    metrics.update(spectral_metrics(audio, sr))
    metrics.update(mid_side_metrics(audio))

    return metrics


def delta_metrics(
    original_metrics: dict[str, float | int],
    processed_metrics: dict[str, float | int],
) -> dict[str, float]:
    keys = [
        "peak_dbfs",
        "rms_dbfs",
        "integrated_lufs",
        "spectral_centroid_hz",
        "spectral_rolloff_95_hz",
        "spectral_flatness",
        "lr_correlation",
        "side_share_pct",
    ]

    deltas: dict[str, float] = {}

    for key in keys:
        value_original = original_metrics.get(key)
        value_processed = processed_metrics.get(key)

        if isinstance(value_original, (int, float)) and isinstance(value_processed, (int, float)):
            deltas[key] = float(value_processed - value_original)

    return deltas


# ============================================================
# PSD / BANDES
# ============================================================

def compute_welch_psd(audio: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    mono = mono_mix(audio)

    freqs, psd = signal.welch(
        mono,
        fs=sr,
        nperseg=8192,
        noverlap=4096,
        scaling="density",
    )

    return freqs, psd


def integrate_band_power(
    freqs: np.ndarray,
    psd: np.ndarray,
    low_hz: float,
    high_hz: float,
) -> float:
    mask = (freqs >= low_hz) & (freqs < high_hz)

    if not np.any(mask):
        return 0.0

    return float(np.trapz(psd[mask], freqs[mask]))


def band_energy_table(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> list[dict[str, float | str]]:
    freqs_o, psd_o = compute_welch_psd(original, sr)
    freqs_p, psd_p = compute_welch_psd(processed, sr)

    total_o = integrate_band_power(freqs_o, psd_o, 20, sr / 2)
    total_p = integrate_band_power(freqs_p, psd_p, 20, sr / 2)

    rows: list[dict[str, float | str]] = []

    for low, high in BANDS_HZ:
        power_o = integrate_band_power(freqs_o, psd_o, low, high)
        power_p = integrate_band_power(freqs_p, psd_p, low, high)

        share_o = power_o / total_o * 100.0 if total_o > 0 else float("nan")
        share_p = power_p / total_p * 100.0 if total_p > 0 else float("nan")

        rows.append(
            {
                "band": f"{low}-{high} Hz",
                "low_hz": float(low),
                "high_hz": float(high),
                "original_power_db": power_to_db(power_o),
                "processed_power_db": power_to_db(power_p),
                "delta_power_db": db_ratio(power_p, power_o),
                "original_share_pct": float(share_o),
                "processed_share_pct": float(share_p),
                "delta_share_pp": float(share_p - share_o),
            }
        )

    return rows


def high_frequency_summary(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> list[dict[str, float | str]]:
    freqs_o, psd_o = compute_welch_psd(original, sr)
    freqs_p, psd_p = compute_welch_psd(processed, sr)

    total_o = integrate_band_power(freqs_o, psd_o, 20, sr / 2)
    total_p = integrate_band_power(freqs_p, psd_p, 20, sr / 2)

    rows: list[dict[str, float | str]] = []

    for threshold in HIGH_FREQ_THRESHOLDS:
        power_o = integrate_band_power(freqs_o, psd_o, threshold, sr / 2)
        power_p = integrate_band_power(freqs_p, psd_p, threshold, sr / 2)

        share_o = power_o / total_o * 100.0 if total_o > 0 else float("nan")
        share_p = power_p / total_p * 100.0 if total_p > 0 else float("nan")

        rows.append(
            {
                "range": f">={threshold} Hz",
                "threshold_hz": float(threshold),
                "original_share_pct": float(share_o),
                "processed_share_pct": float(share_p),
                "delta_share_pp": float(share_p - share_o),
                "delta_power_db": db_ratio(power_p, power_o),
            }
        )

    return rows


# ============================================================
# RÉSIDU
# ============================================================

def residual_global_metrics(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> dict[str, float]:
    residual = processed - original

    residual_rms = rms_linear(residual)
    original_rms = rms_linear(original)

    residual_peak = float(np.max(np.abs(residual))) if residual.size else 0.0
    original_peak = float(np.max(np.abs(original))) if original.size else 0.0

    return {
        "residual_peak_dbfs": amplitude_to_db(residual_peak),
        "residual_rms_dbfs": amplitude_to_db(residual_rms),
        "residual_integrated_lufs": integrated_lufs(residual, sr),
        "residual_rms_vs_original_db": db_ratio(
            residual_rms * residual_rms,
            original_rms * original_rms,
        ),
        "residual_rms_pct_of_original_rms": (
            float((residual_rms / original_rms) * 100.0)
            if original_rms > 0
            else float("nan")
        ),
        "residual_peak_vs_original_peak_db": db_ratio(
            residual_peak * residual_peak,
            original_peak * original_peak,
        ),
    }


def residual_band_table(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> list[dict[str, float | str]]:
    residual = processed - original

    freqs_o, psd_o = compute_welch_psd(original, sr)
    freqs_r, psd_r = compute_welch_psd(residual, sr)

    total_residual = integrate_band_power(freqs_r, psd_r, 20, sr / 2)

    rows: list[dict[str, float | str]] = []

    for low, high in BANDS_HZ:
        original_power = integrate_band_power(freqs_o, psd_o, low, high)
        residual_power = integrate_band_power(freqs_r, psd_r, low, high)

        residual_share = (
            residual_power / total_residual * 100.0
            if total_residual > 0
            else float("nan")
        )

        rows.append(
            {
                "band": f"{low}-{high} Hz",
                "low_hz": float(low),
                "high_hz": float(high),
                "residual_power_db": power_to_db(residual_power),
                "residual_vs_original_band_db": db_ratio(
                    residual_power,
                    original_power,
                ),
                "residual_share_pct_of_total_residual": float(residual_share),
            }
        )

    return rows


def residual_high_frequency_summary(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> list[dict[str, float | str]]:
    residual = processed - original

    freqs_o, psd_o = compute_welch_psd(original, sr)
    freqs_r, psd_r = compute_welch_psd(residual, sr)

    total_residual = integrate_band_power(freqs_r, psd_r, 20, sr / 2)

    rows: list[dict[str, float | str]] = []

    for threshold in HIGH_FREQ_THRESHOLDS:
        original_power = integrate_band_power(freqs_o, psd_o, threshold, sr / 2)
        residual_power = integrate_band_power(freqs_r, psd_r, threshold, sr / 2)

        residual_share = (
            residual_power / total_residual * 100.0
            if total_residual > 0
            else float("nan")
        )

        rows.append(
            {
                "range": f">={threshold} Hz",
                "threshold_hz": float(threshold),
                "residual_power_db": power_to_db(residual_power),
                "residual_vs_original_range_db": db_ratio(
                    residual_power,
                    original_power,
                ),
                "residual_share_pct_of_total_residual": float(residual_share),
            }
        )

    return rows


# ============================================================
# EXPORT WAV DE DIFFÉRENCE
# ============================================================

def filter_high_frequency_residual(
    residual: np.ndarray,
    sr: int,
    low_hz: float = 8000.0,
    high_hz: float = 23500.0,
) -> np.ndarray:
    sos_high = signal.butter(
        6,
        low_hz,
        btype="highpass",
        fs=sr,
        output="sos",
    )

    sos_low = signal.butter(
        6,
        high_hz,
        btype="lowpass",
        fs=sr,
        output="sos",
    )

    filtered_channels: list[np.ndarray] = []

    for channel_index in range(residual.shape[1]):
        channel = residual[:, channel_index]
        channel = signal.sosfiltfilt(sos_high, channel)
        channel = signal.sosfiltfilt(sos_low, channel)
        filtered_channels.append(channel)

    return np.stack(filtered_channels, axis=1)


def write_difference_files(
    output_dir: Path,
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> dict[str, str]:
    residual = processed - original
    residual_hf = filter_high_frequency_residual(residual, sr)

    full_path = output_dir / "difference_full_processed_minus_original.wav"
    hf_path = output_dir / "difference_highfreq_8k_23k5.wav"

    sf.write(
        full_path,
        np.clip(residual, -1.0, 1.0),
        sr,
        subtype="PCM_24",
    )

    sf.write(
        hf_path,
        np.clip(residual_hf, -1.0, 1.0),
        sr,
        subtype="PCM_24",
    )

    return {
        "difference_full_wav": str(full_path),
        "difference_highfreq_wav": str(hf_path),
    }


# ============================================================
# GRAPHIQUES 1D
# ============================================================

def save_spectrum_plots(
    output_dir: Path,
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> None:
    freqs_o, psd_o = compute_welch_psd(original, sr)
    freqs_p, psd_p = compute_welch_psd(processed, sr)

    db_o = 10.0 * np.log10(np.maximum(psd_o, EPSILON))
    db_p = 10.0 * np.log10(np.maximum(psd_p, EPSILON))

    # Normalisation visuelle relative.
    common_max = max(float(np.max(db_o)), float(np.max(db_p)))
    db_o_rel = db_o - common_max
    db_p_rel = db_p - common_max

    valid = freqs_o >= 20

    plt.figure(figsize=(16, 8))
    plt.semilogx(freqs_o[valid], db_o_rel[valid], label="Original")
    plt.semilogx(freqs_p[valid], db_p_rel[valid], label="Traité")
    plt.title("Spectre moyen — Original vs traité")
    plt.xlabel("Fréquence (Hz)")
    plt.ylabel("Amplitude moyenne relative (dB)")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "01_spectre_moyen_original_vs_processed.png", dpi=180)
    plt.close()

    delta_db = db_p - db_o

    plt.figure(figsize=(16, 8))
    plt.semilogx(freqs_o[valid], delta_db[valid])
    plt.axhline(0.0, linewidth=1)
    plt.title("Différence spectrale — traité moins original")
    plt.xlabel("Fréquence (Hz)")
    plt.ylabel("Δ amplitude spectrale (dB)")
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(output_dir / "02_difference_spectrale_processed_minus_original.png", dpi=180)
    plt.close()


def save_band_plots(
    output_dir: Path,
    band_rows: list[dict[str, float | str]],
) -> None:
    labels = [str(row["band"]) for row in band_rows]
    delta_db = [float(row["delta_power_db"]) for row in band_rows]
    original_shares = [float(row["original_share_pct"]) for row in band_rows]
    processed_shares = [float(row["processed_share_pct"]) for row in band_rows]

    x = np.arange(len(labels))

    plt.figure(figsize=(16, 7))
    plt.bar(x, delta_db)
    plt.axhline(0.0, linewidth=1)
    plt.xticks(x, labels, rotation=35, ha="right")
    plt.ylabel("Δ puissance intégrée (dB)")
    plt.title("Ajout / retrait de puissance par bande — traité moins original")
    plt.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(output_dir / "03_delta_puissance_par_bande.png", dpi=180)
    plt.close()

    width = 0.38

    plt.figure(figsize=(16, 7))
    plt.bar(x - width / 2, original_shares, width, label="Original")
    plt.bar(x + width / 2, processed_shares, width, label="Traité")
    plt.xticks(x, labels, rotation=35, ha="right")
    plt.ylabel("Part de la puissance totale (%)")
    plt.title("Poids relatif de chaque bande dans le mix")
    plt.grid(axis="y", alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "04_part_energie_par_bande.png", dpi=180)
    plt.close()


# ============================================================
# SPECTROGRAMMES
# ============================================================

def compute_spectrogram_db(
    audio: np.ndarray,
    sr: int,
) -> tuple[np.ndarray, np.ndarray]:
    mono = mono_mix(audio)

    stft = librosa.stft(
        mono.astype(np.float32),
        n_fft=STFT_N_FFT,
        hop_length=STFT_HOP,
        window="hann",
    )

    magnitude = np.abs(stft)

    return magnitude, librosa.fft_frequencies(sr=sr, n_fft=STFT_N_FFT)


def save_spectrogram_plots(
    output_dir: Path,
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
) -> None:
    mag_o, freqs = compute_spectrogram_db(original, sr)
    mag_p, _ = compute_spectrogram_db(processed, sr)
    mag_r, _ = compute_spectrogram_db(processed - original, sr)

    common_ref = max(float(np.max(mag_o)), float(np.max(mag_p)), EPSILON)

    db_o = librosa.amplitude_to_db(mag_o, ref=common_ref, top_db=80.0)
    db_p = librosa.amplitude_to_db(mag_p, ref=common_ref, top_db=80.0)
    db_r = librosa.amplitude_to_db(mag_r, ref=common_ref, top_db=100.0)

    delta_db = db_p - db_o

    def plot_spec(
        data: np.ndarray,
        filename: str,
        title: str,
        vmin: float,
        vmax: float,
        y_min: float = 20.0,
        y_max: float | None = None,
        cmap: str | None = None,
    ) -> None:
        plt.figure(figsize=(16, 8))

        librosa.display.specshow(
            data,
            sr=sr,
            hop_length=STFT_HOP,
            x_axis="time",
            y_axis="log",
            vmin=vmin,
            vmax=vmax,
            cmap=cmap,
        )

        plt.ylim(y_min, y_max or sr / 2)
        plt.colorbar(format="%+2.0f dB")
        plt.title(title)
        plt.tight_layout()
        plt.savefig(output_dir / filename, dpi=180)
        plt.close()

    plot_spec(
        db_o,
        "05_spectrogramme_original_echelle_commune.png",
        "Spectrogramme — Original — échelle commune",
        -80.0,
        0.0,
    )

    plot_spec(
        db_p,
        "06_spectrogramme_processed_echelle_commune.png",
        "Spectrogramme — Traité — échelle commune",
        -80.0,
        0.0,
    )

    plot_spec(
        delta_db,
        "07_spectrogramme_difference_relative_processed_minus_original.png",
        "Spectrogramme de différence relative — traité moins original",
        -20.0,
        40.0,
        cmap="coolwarm",
    )

    plot_spec(
        db_r,
        "08_spectrogramme_residu_echelle_commune.png",
        "Spectrogramme du résidu traité - original — échelle commune",
        -100.0,
        0.0,
    )

    plot_spec(
        db_o,
        "09_zoom_hf_original_8k_24k.png",
        "Zoom hautes fréquences — Original",
        -80.0,
        0.0,
        y_min=8000.0,
        y_max=sr / 2,
    )

    plot_spec(
        db_p,
        "10_zoom_hf_processed_8k_24k.png",
        "Zoom hautes fréquences — Traité",
        -80.0,
        0.0,
        y_min=8000.0,
        y_max=sr / 2,
    )

    plot_spec(
        delta_db,
        "11_zoom_hf_difference_relative_8k_24k.png",
        "Zoom hautes fréquences — Différence relative",
        -20.0,
        40.0,
        y_min=8000.0,
        y_max=sr / 2,
        cmap="coolwarm",
    )

    plot_spec(
        db_r,
        "12_zoom_hf_residu_8k_24k.png",
        "Zoom hautes fréquences — Résidu traité - original",
        -100.0,
        0.0,
        y_min=8000.0,
        y_max=sr / 2,
    )


# ============================================================
# ÉVOLUTION TEMPORELLE DU RÉSIDU
# ============================================================

def save_residual_time_plot(
    output_dir: Path,
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
    chunk_size_s: float | None,
    chunk_overlap_fraction: float | None,
) -> None:
    residual = mono_mix(processed - original)

    frame_length = int(sr * 0.25)
    hop_length = int(sr * 0.05)

    rms = librosa.feature.rms(
        y=residual.astype(np.float32),
        frame_length=frame_length,
        hop_length=hop_length,
    )[0]

    times = librosa.frames_to_time(
        np.arange(len(rms)),
        sr=sr,
        hop_length=hop_length,
    )

    rms_db = 20.0 * np.log10(np.maximum(rms, EPSILON))

    plt.figure(figsize=(16, 7))
    plt.plot(times, rms_db, label="RMS de la différence")

    if chunk_size_s and chunk_overlap_fraction is not None:
        chunk_step_s = chunk_size_s * (1.0 - chunk_overlap_fraction)
        current = chunk_step_s
        total_duration = len(original) / sr

        while current < total_duration:
            plt.axvline(
                current,
                linestyle="--",
                alpha=0.25,
            )
            current += chunk_step_s

    plt.title("Évolution temporelle de la différence traité - original")
    plt.xlabel("Temps (s)")
    plt.ylabel("RMS différence (dBFS)")
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "13_rms_difference_dans_le_temps.png", dpi=180)
    plt.close()


# ============================================================
# EXPORT JSON / CSV
# ============================================================

def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    fieldnames = list(rows[0].keys())

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)

    if isinstance(value, np.generic):
        return value.item()

    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}

    if isinstance(value, list):
        return [json_safe(item) for item in value]

    return value


# ============================================================
# PIPELINE PRINCIPAL D’ANALYSE
# ============================================================

def run_audio_analysis(
    *,
    original_wav: Path,
    processed_wav: Path,
    output_dir: Path,
    chunk_size_s: float | None,
    chunk_overlap_fraction: float | None,
    label: str,
    log: LogCallback,
    progress: ProgressCallback,
) -> dict[str, Any]:
    total_steps = 10
    step = 0

    output_dir.mkdir(parents=True, exist_ok=True)

    def advance(message: str) -> None:
        nonlocal step
        step += 1
        log(message)
        progress(step, total_steps)

    advance("Diagnostic des fichiers source...")
    source_original = source_diagnostics(original_wav)
    source_processed = source_diagnostics(processed_wav)

    advance("Préparation de la paire audio alignée...")
    pair = prepare_audio_pair(
        original_wav,
        processed_wav,
        log=log,
    )

    advance("Calcul des métriques globales...")
    original_metrics = global_metrics(pair.original, pair.sample_rate)
    processed_metrics = global_metrics(pair.processed, pair.sample_rate)
    deltas = delta_metrics(original_metrics, processed_metrics)

    advance("Calcul des métriques de résidu...")
    residual_metrics = residual_global_metrics(
        pair.original,
        pair.processed,
        pair.sample_rate,
    )

    advance("Calcul des énergies par bandes...")
    band_rows = band_energy_table(
        pair.original,
        pair.processed,
        pair.sample_rate,
    )
    hf_rows = high_frequency_summary(
        pair.original,
        pair.processed,
        pair.sample_rate,
    )

    residual_band_rows = residual_band_table(
        pair.original,
        pair.processed,
        pair.sample_rate,
    )
    residual_hf_rows = residual_high_frequency_summary(
        pair.original,
        pair.processed,
        pair.sample_rate,
    )

    advance("Écriture des WAV de différence...")
    difference_files = write_difference_files(
        output_dir,
        pair.original,
        pair.processed,
        pair.sample_rate,
    )

    advance("Génération des graphes spectraux...")
    save_spectrum_plots(
        output_dir,
        pair.original,
        pair.processed,
        pair.sample_rate,
    )
    save_band_plots(
        output_dir,
        band_rows,
    )

    advance("Génération des spectrogrammes...")
    save_spectrogram_plots(
        output_dir,
        pair.original,
        pair.processed,
        pair.sample_rate,
    )

    advance("Génération de la courbe temporelle du résidu...")
    save_residual_time_plot(
        output_dir,
        pair.original,
        pair.processed,
        pair.sample_rate,
        chunk_size_s=chunk_size_s,
        chunk_overlap_fraction=chunk_overlap_fraction,
    )

    advance("Écriture des rapports JSON / CSV...")

    report = {
        "label": label,
        "paths": {
            "original_wav": str(original_wav),
            "processed_wav": str(processed_wav),
            "output_dir": str(output_dir),
            **difference_files,
        },
        "alignment": {
            "lag_samples_positive_means_processed_delayed": pair.alignment_lag_samples,
            "lag_ms_positive_means_processed_delayed": pair.alignment_lag_ms,
        },
        "source_file_diagnostics_original": source_original.__dict__,
        "source_file_diagnostics_processed": source_processed.__dict__,
        "global_metrics_original": original_metrics,
        "global_metrics_processed": processed_metrics,
        "global_metric_deltas_processed_minus_original": deltas,
        "residual_global_metrics_processed_minus_original": residual_metrics,
        "band_energy": band_rows,
        "high_frequency_summary": hf_rows,
        "residual_band_energy": residual_band_rows,
        "residual_high_frequency_summary": residual_hf_rows,
        "analysis_context": {
            "chunk_size_s": chunk_size_s,
            "chunk_overlap_fraction": chunk_overlap_fraction,
        },
    }

    report_path = output_dir / "analysis_report.json"

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(
            json_safe(report),
            file,
            ensure_ascii=False,
            indent=2,
        )

    write_csv(output_dir / "band_energy_table.csv", band_rows)
    write_csv(output_dir / "high_frequency_summary.csv", hf_rows)
    write_csv(output_dir / "residual_band_energy_table.csv", residual_band_rows)
    write_csv(output_dir / "residual_high_frequency_summary.csv", residual_hf_rows)

    summary = {
        "report_json": str(report_path),
        "output_dir": str(output_dir),
        "difference_full_wav": difference_files["difference_full_wav"],
        "difference_highfreq_wav": difference_files["difference_highfreq_wav"],
        "metrics": {
            "rms_delta_db": deltas.get("rms_dbfs"),
            "lufs_delta": deltas.get("integrated_lufs"),
            "spectral_centroid_delta_hz": deltas.get("spectral_centroid_hz"),
            "spectral_rolloff_95_delta_hz": deltas.get("spectral_rolloff_95_hz"),
            "residual_rms_pct_of_original_rms": residual_metrics.get(
                "residual_rms_pct_of_original_rms"
            ),
            "residual_rms_vs_original_db": residual_metrics.get(
                "residual_rms_vs_original_db"
            ),
        },
        "high_frequency_summary": hf_rows,
        "residual_high_frequency_summary": residual_hf_rows,
    }

    return {
        "report": report,
        "summary": summary,
    }