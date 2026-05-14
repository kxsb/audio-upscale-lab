from __future__ import annotations

import gc
import os
import random
from pathlib import Path
from typing import Any, Callable

import librosa
import numpy as np
import pyloudnorm as pyln
import soundfile as sf
import torch
from audiosr import build_model, super_resolution
from scipy import signal


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]


# ============================================================
# OUTILS AUDIO
# ============================================================

def match_array_shapes(array_1: np.ndarray, array_2: np.ndarray) -> np.ndarray:
    """
    Ajuste array_1 à la forme de array_2.
    Utilisé pour le mode multiband ensemble.
    """
    if (len(array_1.shape) == 1) and (len(array_2.shape) == 1):
        if array_1.shape[0] > array_2.shape[0]:
            array_1 = array_1[: array_2.shape[0]]
        elif array_1.shape[0] < array_2.shape[0]:
            array_1 = np.pad(
                array_1,
                (array_2.shape[0] - array_1.shape[0], 0),
                "constant",
                constant_values=0,
            )
    else:
        if array_1.shape[1] > array_2.shape[1]:
            array_1 = array_1[:, : array_2.shape[1]]
        elif array_1.shape[1] < array_2.shape[1]:
            padding = array_2.shape[1] - array_1.shape[1]
            array_1 = np.pad(
                array_1,
                ((0, 0), (0, padding)),
                "constant",
                constant_values=0,
            )

    return array_1


def lowpass_for_audiosr(
    audio: np.ndarray,
    cutoff: float,
    sr: int = 48000,
    order: int = 8,
) -> np.ndarray:
    """
    Préfiltre l'entrée à cutoff Hz tout en conservant un fichier 48 kHz.

    C'est préférable à une baisse artificielle du sample rate :
    - AudioSR garde une entrée 48 kHz compatible avec son pipeline interne ;
    - on impose quand même un cutoff contrôlé pour guider la reconstruction.
    """
    nyquist = sr / 2

    if not 0 < cutoff < nyquist:
        raise ValueError(
            f"Cutoff invalide : {cutoff} Hz. "
            f"Il doit être strictement compris entre 0 et {nyquist} Hz."
        )

    sos = signal.butter(
        order,
        cutoff,
        btype="low",
        fs=sr,
        output="sos",
    )

    if audio.ndim == 1:
        filtered = signal.sosfiltfilt(sos, audio)
        return filtered.astype(np.float32)

    filtered_channels = []

    for channel_index in range(audio.shape[1]):
        filtered_channel = signal.sosfiltfilt(
            sos,
            audio[:, channel_index],
        )
        filtered_channels.append(filtered_channel)

    return np.stack(filtered_channels, axis=1).astype(np.float32)

def lr_filter(
    audio: np.ndarray,
    cutoff: float,
    filter_type: str,
    order: int = 12,
    sr: int = 48000,
) -> np.ndarray:
    """
    Filtre Linkwitz-Riley approximé.
    """
    audio = audio.T

    b, a = signal.butter(
        order // 2,
        cutoff,
        btype=filter_type,
        analog=False,
        fs=sr,
    )

    sos = signal.tf2sos(b, a)
    filtered_audio = signal.sosfiltfilt(sos, audio)

    return filtered_audio.T


def safe_integrated_loudness(meter: pyln.Meter, audio: np.ndarray) -> float | None:
    """
    Évite que pyloudnorm casse sur un chunk trop silencieux.
    """
    try:
        loudness = meter.integrated_loudness(audio)

        if np.isfinite(loudness):
            return float(loudness)

        return None
    except Exception:
        return None


def normalize_chunk_loudness(
    chunk: np.ndarray,
    meter_after: pyln.Meter,
    target_loudness: float | None,
) -> np.ndarray:
    """
    Ramène le chunk traité vers la loudness du chunk original quand c'est possible.
    """
    if target_loudness is None:
        return chunk

    loudness_after = safe_integrated_loudness(meter_after, chunk)

    if loudness_after is None:
        return chunk

    try:
        return pyln.normalize.loudness(
            chunk,
            loudness_after,
            target_loudness,
        )
    except Exception:
        return chunk


# ============================================================
# UPSCALE AUDIO SR
# ============================================================

def run_audiosr_upscale(
    *,
    input_wav: Path,
    output_wav: Path,
    settings: dict[str, Any],
    log: LogCallback,
    progress: ProgressCallback,
) -> dict[str, Any]:
    """
    Lance AudioSR sur un WAV stéréo 48 kHz.

    Le modèle reconstruit le spectre jusqu'à 48 kHz de sortie.
    Les canaux gauche/droite sont traités séparément,
    avec chunks + overlap + crossfade.
    """
    os.environ["TOKENIZERS_PARALLELISM"] = "true"
    torch.set_float32_matmul_precision("high")

    model_name = str(settings.get("model_name", "basic"))
    device = str(settings.get("device", "cuda:0"))
    chunk_size = float(settings.get("chunk_size", 5.12))
    overlap = float(settings.get("overlap", 0.04))
    ddim_steps = int(settings.get("ddim_steps", 50))
    guidance_scale = float(settings.get("guidance_scale", 3.5))
    seed = int(settings.get("seed", 0))
    multiband_ensemble = bool(settings.get("multiband_ensemble", False))
    input_cutoff = int(settings.get("input_cutoff", 12000))

    if seed == 0:
        seed = random.randint(0, 2**32 - 1)

    output_sr = 48000
    input_sr = 48000
    sample_rate_ratio = 1.0
    crossover_freq = input_cutoff - 1000

    log("Chargement du modèle AudioSR...")
    log(f"Modèle : {model_name}")
    log(f"Appareil : {device}")
    log(f"Seed : {seed}")
    log(f"Guidance scale : {guidance_scale}")
    log(f"DDIM steps : {ddim_steps}")
    log(f"Chunk size : {chunk_size} s")
    log(f"Overlap : {overlap}")
    log(f"Input cutoff : {input_cutoff} Hz")
    log(f"Multiband ensemble : {'oui' if multiband_ensemble else 'non'}")

    model = build_model(
        model_name=model_name,
        device=device,
    )

    log("Modèle AudioSR chargé.")
    log("Chargement du fichier de référence...")

    audio, _ = librosa.load(
        str(input_wav),
        sr=input_sr,
        mono=False,
    )

    audio = audio.T

    if audio.ndim == 1:
        audio = audio[:, None]

    if input_cutoff < output_sr / 2:
        log(
            f"Préfiltrage low-pass de l’entrée à {input_cutoff} Hz "
            "pour guider AudioSR."
        )

        audio = lowpass_for_audiosr(
            audio,
            cutoff=input_cutoff,
            sr=input_sr,
            order=8,
        )
        
    is_stereo = audio.shape[1] == 2

    if is_stereo:
        audio_channels = [audio[:, 0], audio[:, 1]]
        log("Audio stéréo détecté.")
    else:
        audio_channels = [audio[:, 0]]
        log("Audio mono détecté.")

    chunk_samples = int(chunk_size * input_sr)
    overlap_samples = int(overlap * chunk_samples)
    output_chunk_samples = int(chunk_size * output_sr)
    output_overlap_samples = int(overlap * output_chunk_samples)
    enable_overlap = overlap > 0

    def process_chunks(channel_audio: np.ndarray) -> tuple[list[np.ndarray], list[int]]:
        chunks: list[np.ndarray] = []
        original_lengths: list[int] = []

        start = 0
        step = chunk_samples - overlap_samples if enable_overlap else chunk_samples

        while start < len(channel_audio):
            end = min(start + chunk_samples, len(channel_audio))
            chunk = channel_audio[start:end]

            if len(chunk) < chunk_samples:
                original_lengths.append(len(chunk))
                chunk = np.concatenate(
                    [chunk, np.zeros(chunk_samples - len(chunk))]
                )
            else:
                original_lengths.append(chunk_samples)

            chunks.append(chunk)
            start += step

        return chunks, original_lengths

    chunks_per_channel = [
        process_chunks(channel)
        for channel in audio_channels
    ]

    total_chunks = sum(len(chunks) for chunks, _ in chunks_per_channel)
    done_chunks = 0

    total_length = (
        len(chunks_per_channel[0][0]) * output_chunk_samples
        - (len(chunks_per_channel[0][0]) - 1)
        * (output_overlap_samples if enable_overlap else 0)
    )

    reconstructed_channels = [
        np.zeros((1, total_length), dtype=np.float32)
        for _ in audio_channels
    ]

    meter_before = pyln.Meter(input_sr)
    meter_after = pyln.Meter(output_sr)

    temp_dir = output_wav.parent / "_temp_audiosr"
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        for ch_idx, (chunks, original_lengths) in enumerate(chunks_per_channel):
            channel_name = "gauche / mono" if ch_idx == 0 else "droite"

            for i, chunk in enumerate(chunks):
                done_chunks += 1

                log(
                    f"Traitement chunk {i + 1}/{len(chunks)} "
                    f"— canal {channel_name} "
                    f"({done_chunks}/{total_chunks})"
                )

                progress(done_chunks, total_chunks)

                loudness_before = safe_integrated_loudness(
                    meter_before,
                    chunk,
                )

                temp_wav_path = temp_dir / f"chunk_ch{ch_idx}_{i:04d}.wav"

                sf.write(
                    temp_wav_path,
                    chunk,
                    input_sr,
                )

                out_chunk = super_resolution(
                    model,
                    str(temp_wav_path),
                    seed=seed,
                    guidance_scale=guidance_scale,
                    ddim_steps=ddim_steps,
                    latent_t_per_second=12.8,
                )

                try:
                    temp_wav_path.unlink(missing_ok=True)
                except Exception:
                    pass

                out_chunk = out_chunk[0]

                num_samples_to_keep = int(original_lengths[i] * sample_rate_ratio)

                out_chunk = out_chunk[:, :num_samples_to_keep].squeeze()

                out_chunk = normalize_chunk_loudness(
                    out_chunk,
                    meter_after,
                    loudness_before,
                )

                if enable_overlap:
                    actual_overlap_samples = min(
                        output_overlap_samples,
                        num_samples_to_keep,
                    )

                    fade_out = np.linspace(
                        1.0,
                        0.0,
                        actual_overlap_samples,
                    )

                    fade_in = np.linspace(
                        0.0,
                        1.0,
                        actual_overlap_samples,
                    )

                    if i == 0:
                        out_chunk[-actual_overlap_samples:] *= fade_out
                    elif i < len(chunks) - 1:
                        out_chunk[:actual_overlap_samples] *= fade_in
                        out_chunk[-actual_overlap_samples:] *= fade_out
                    else:
                        out_chunk[:actual_overlap_samples] *= fade_in

                start = i * (
                    output_chunk_samples - output_overlap_samples
                    if enable_overlap
                    else output_chunk_samples
                )

                end = start + out_chunk.shape[0]

                reconstructed_channels[ch_idx][0, start:end] += out_chunk.flatten()

    finally:
        try:
            for temp_file in temp_dir.glob("*.wav"):
                temp_file.unlink(missing_ok=True)
            temp_dir.rmdir()
        except Exception:
            pass

    reconstructed_audio = (
        np.stack(reconstructed_channels, axis=-1)
        if is_stereo
        else reconstructed_channels[0]
    )

    if multiband_ensemble:
        log("Application du multiband ensemble...")

        low, _ = librosa.load(
            str(input_wav),
            sr=output_sr,
            mono=False,
        )

        output = match_array_shapes(
            reconstructed_audio[0].T,
            low,
        )

        low = lr_filter(
            low.T,
            crossover_freq,
            "lowpass",
            order=10,
            sr=output_sr,
        )

        high = lr_filter(
            output.T,
            crossover_freq,
            "highpass",
            order=10,
            sr=output_sr,
        )

        high = lr_filter(
            high,
            23000,
            "lowpass",
            order=2,
            sr=output_sr,
        )

        output = low + high
    else:
        output = reconstructed_audio[0]

    # Correction importante :
    # AudioSR préalloue la longueur théorique des chunks,
    # ce qui peut laisser une queue silencieuse.
    # On coupe donc à la longueur attendue.
    expected_output_length = int(round(len(audio) * sample_rate_ratio))

    if output.ndim == 1:
        output = output[:expected_output_length]
    else:
        output = output[:expected_output_length, :]

    output_wav.parent.mkdir(parents=True, exist_ok=True)

    log("Écriture du WAV upscalé...")

    sf.write(
        output_wav,
        data=output,
        samplerate=output_sr,
        subtype="PCM_24",
    )

    log("WAV upscalé créé.")

    del model
    gc.collect()

    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "output_wav": str(output_wav),
        "settings": {
            "model_name": model_name,
            "device": device,
            "chunk_size": chunk_size,
            "overlap": overlap,
            "ddim_steps": ddim_steps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "multiband_ensemble": multiband_ensemble,
            "input_cutoff": input_cutoff,
        },
    }