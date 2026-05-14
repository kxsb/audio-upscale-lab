from __future__ import annotations

import importlib.util

import json
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


import yt_dlp
from yt_dlp.version import __version__ as YTDLP_VERSION


# ============================================================
# OUTILS GÉNÉRAUX
# ============================================================

def slugify(value: str, max_length: int = 70) -> str:
    """
    Transforme un titre en identifiant de dossier lisible :
    "Anna Kova - De Passage" -> "anna-kova-de-passage"
    """
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value[:max_length] or "untitled"


def ensure_executable(command: str) -> str:
    """
    Vérifie qu'un exécutable est accessible dans le PATH.
    """
    path = shutil.which(command)

    if not path:
        raise RuntimeError(
            f"Le programme '{command}' est introuvable dans le PATH."
        )

    return path


def run_command(
    command: list[str],
    error_prefix: str,
) -> subprocess.CompletedProcess[str]:
    """
    Exécute une commande système et remonte une erreur lisible si elle échoue.
    """
    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if process.returncode != 0:
        stderr_tail = "\n".join(process.stderr.splitlines()[-30:])
        raise RuntimeError(
            f"{error_prefix}\n\n{stderr_tail}"
        )

    return process


# ============================================================
# DÉPENDANCES
# ============================================================

def check_runtime_dependencies() -> dict[str, Any]:
    """
    Retourne l'état des dépendances utiles à l'application.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    deno_path = shutil.which("deno")

    yt_dlp_ejs_available = (
        importlib.util.find_spec("yt_dlp_ejs") is not None
    )
    
    return {
        "yt_dlp": {
            "available": True,
            "version": YTDLP_VERSION,
        },
        "yt_dlp_ejs": {
            "available": yt_dlp_ejs_available,
        },
        "deno": {
            "available": bool(deno_path),
            "path": deno_path,
        },
        "ffmpeg": {
            "available": bool(ffmpeg_path),
            "path": ffmpeg_path,
        },
        "ffprobe": {
            "available": bool(ffprobe_path),
            "path": ffprobe_path,
        },
    }

# ============================================================
# YT-DLP
# ============================================================

class YtDlpLogger:
    """
    Petit logger qui récupère uniquement les messages utiles
    pour les renvoyer à l'interface.
    """

    def __init__(self, logs: list[str]) -> None:
        self.logs = logs

    def debug(self, message: str) -> None:
        # yt-dlp envoie énormément de messages debug.
        # On les ignore pour ne pas noyer l'interface.
        pass

    def info(self, message: str) -> None:
        if message:
            self.logs.append(message)

    def warning(self, message: str) -> None:
        self.logs.append(f"AVERTISSEMENT yt-dlp : {message}")

    def error(self, message: str) -> None:
        self.logs.append(f"ERREUR yt-dlp : {message}")


def extract_youtube_metadata(url: str) -> dict[str, Any]:
    """
    Récupère les métadonnées principales de la vidéo sans la télécharger.
    """
    options = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise RuntimeError(
            "Impossible de récupérer les métadonnées de la vidéo."
        )

    # Sécurité : si yt-dlp renvoie malgré tout une structure de playlist,
    # on prend la première entrée exploitable.
    if "entries" in info:
        entries = [entry for entry in info["entries"] if entry]

        if not entries:
            raise RuntimeError(
                "Aucune entrée exploitable dans cette URL."
            )

        info = entries[0]

    return {
        "id": info.get("id") or "unknown-id",
        "title": info.get("title") or "Titre inconnu",
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "webpage_url": info.get("webpage_url") or url,
    }


def download_best_audio(
    url: str,
    source_dir: Path,
    logs: list[str],
) -> Path:
    """
    Télécharge le meilleur flux audio disponible.

    Priorité :
    1. WebM/Opus
    2. Tout flux Opus
    3. Meilleur audio disponible sinon
    """
    source_dir.mkdir(parents=True, exist_ok=True)

    outtmpl = str(source_dir / "source.%(ext)s")

    def progress_hook(progress: dict[str, Any]) -> None:
        if progress.get("status") == "finished":
            logs.append("Téléchargement audio terminé.")

    options = {
        "format": (
            "bestaudio[ext=webm][acodec^=opus]/"
            "bestaudio[acodec^=opus]/"
            "bestaudio/best"
        ),
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "overwrites": True,
        "logger": YtDlpLogger(logs),
        "progress_hooks": [progress_hook],
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.extract_info(url, download=True)

    candidates = [
        path
        for path in source_dir.glob("source.*")
        if path.suffix.lower() not in {".part", ".ytdl", ".temp"}
    ]

    if not candidates:
        raise RuntimeError(
            "Le téléchargement semble terminé, mais aucun fichier source n’a été trouvé."
        )

    # En théorie il n'y en a qu'un.
    # On prend le plus récent par sécurité.
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ============================================================
# FFMPEG / FFPROBE
# ============================================================

def convert_to_reference_wav(
    source_file: Path,
    reference_wav: Path,
    logs: list[str],
) -> None:
    """
    Convertit le flux natif en WAV stéréo 48 kHz / PCM 24 bits.

    Ce fichier devient notre référence locale propre pour :
    - écoute A/B ;
    - upscale AudioSR ;
    - analyse avant/après.
    """
    ffmpeg = ensure_executable("ffmpeg")

    reference_wav.parent.mkdir(parents=True, exist_ok=True)

    logs.append(
        "Conversion en référence WAV 48 kHz / PCM 24 bits stéréo..."
    )

    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-i",
        str(source_file),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-c:a",
        "pcm_s24le",
        str(reference_wav),
    ]

    run_command(
        command,
        error_prefix="Échec de la conversion FFmpeg.",
    )

    logs.append("Référence WAV créée.")


def ffprobe_audio(path: Path) -> dict[str, Any]:
    """
    Retourne un diagnostic léger d'un fichier audio via ffprobe.
    """
    ffprobe = ensure_executable("ffprobe")

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration,size,bit_rate:"
            "stream=index,codec_type,codec_name,sample_rate,channels,bit_rate"
        ),
        "-of",
        "json",
        str(path),
    ]

    process = run_command(
        command,
        error_prefix=f"Échec de ffprobe sur {path.name}.",
    )

    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        return {
            "error": "Réponse ffprobe non décodable.",
            "raw": process.stdout,
        }


# ============================================================
# PROJET LOCAL
# ============================================================

def prepare_youtube_project(
    url: str,
    base_dir: Path,
) -> dict[str, Any]:
    """
    Pipeline V1 complet :
    - vérification des dépendances ;
    - métadonnées YouTube ;
    - création d'un dossier projet ;
    - téléchargement du meilleur audio ;
    - conversion en WAV 48 kHz / 24 bits ;
    - ffprobe ;
    - écriture du project.json ;
    - retour des infos vers l'interface.
    """
    logs: list[str] = []

    dependencies = check_runtime_dependencies()

    if not dependencies["ffmpeg"]["available"]:
        raise RuntimeError(
            "FFmpeg est introuvable dans le PATH."
        )

    if not dependencies["ffprobe"]["available"]:
        raise RuntimeError(
            "FFprobe est introuvable dans le PATH."
        )

    logs.append("Récupération des métadonnées YouTube...")
    metadata = extract_youtube_metadata(url)

    project_slug = slugify(metadata["title"])
    project_key = f"{metadata['id']}__{project_slug}"

    projects_root = base_dir / "workspace" / "projects"
    project_dir = projects_root / project_key
    source_dir = project_dir / "source"
    prepared_dir = project_dir / "prepared"

    project_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir.mkdir(parents=True, exist_ok=True)

    logs.append(f"Projet : {metadata['title']}")
    logs.append("Téléchargement du meilleur flux audio disponible...")

    source_file = download_best_audio(
        url=url,
        source_dir=source_dir,
        logs=logs,
    )

    reference_wav = prepared_dir / "reference_48k_pcm24.wav"

    convert_to_reference_wav(
        source_file=source_file,
        reference_wav=reference_wav,
        logs=logs,
    )

    logs.append("Analyse technique rapide des fichiers...")
    source_probe = ffprobe_audio(source_file)
    reference_probe = ffprobe_audio(reference_wav)

    project_payload = {
        "project_key": project_key,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": metadata,
        "paths": {
            "project_dir": str(project_dir),
            "source_dir": str(source_dir),
            "prepared_dir": str(prepared_dir),
            "source_file": str(source_file),
            "reference_wav": str(reference_wav),
        },
        "technical_info": {
            "source_probe": source_probe,
            "reference_probe": reference_probe,
        },
    }

    project_json = project_dir / "project.json"

    with project_json.open("w", encoding="utf-8") as file:
        json.dump(
            project_payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    logs.append("Projet local prêt.")

    return {
        "ok": True,
        "project": project_payload,
        "logs": logs,
    }