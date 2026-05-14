from __future__ import annotations

import json
import os
import threading
import traceback
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.audiosr_runner import run_audiosr_upscale
from backend.audio_analysis_runner import run_audio_analysis
from backend.pipeline import (
    check_runtime_dependencies,
    ffprobe_audio,
    prepare_youtube_project,
)


class AppApi:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

        # Jobs AudioSR maintenus en mémoire pendant l'exécution de l'app.
        self.jobs: dict[str, dict[str, Any]] = {}
        self.jobs_lock = threading.Lock()

    # ========================================================
    # APP / DÉPENDANCES
    # ========================================================

    def ping(self) -> dict[str, Any]:
        return {
            "ok": True,
            "message": "Python bridge ready",
        }

    def check_dependencies(self) -> dict[str, Any]:
        try:
            return {
                "ok": True,
                "dependencies": check_runtime_dependencies(),
            }
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

    # ========================================================
    # PIPELINE SOURCE YOUTUBE
    # ========================================================

    def prepare_youtube_source(self, url: str) -> dict[str, Any]:
        url = (url or "").strip()

        if not url:
            return {
                "ok": False,
                "error": "Aucune URL fournie.",
            }

        try:
            return prepare_youtube_project(
                url=url,
                base_dir=self.base_dir,
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

    # ========================================================
    # UPSCALE AUDIO SR
    # ========================================================

    def start_audiosr_upscale(
        self,
        project_key: str,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Démarre un job AudioSR en arrière-plan.
        """
        settings = settings or {}
        project_key = (project_key or "").strip()

        if not project_key:
            return {
                "ok": False,
                "error": "Clé de projet manquante.",
            }

        try:
            project_payload, project_json_path = self._load_project(project_key)
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

        reference_wav = Path(project_payload["paths"]["reference_wav"])

        if not reference_wav.exists():
            return {
                "ok": False,
                "error": f"Référence WAV introuvable : {reference_wav}",
            }

        job_id = uuid.uuid4().hex[:12]
        created_at = datetime.now().isoformat(timespec="seconds")

        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        upscale_dir = Path(project_payload["paths"]["project_dir"]) / "upscale"
        run_dir = upscale_dir / f"audiosr_{run_stamp}_{job_id[:6]}"
        output_wav = run_dir / "audiosr_upscaled_48k_pcm24.wav"

        run_dir.mkdir(parents=True, exist_ok=True)

        job = {
            "id": job_id,
            "kind": "audiosr_upscale",
            "status": "queued",
            "created_at": created_at,
            "started_at": None,
            "finished_at": None,
            "project_key": project_key,
            "project_json_path": str(project_json_path),
            "input_wav": str(reference_wav),
            "output_wav": str(output_wav),
            "run_dir": str(run_dir),
            "settings": self._normalize_audiosr_settings(settings),
            "progress": {
                "done": 0,
                "total": 0,
                "percent": 0.0,
            },
            "logs": [
                "Job AudioSR créé.",
                f"Projet : {project_key}",
            ],
            "result": None,
            "error": None,
        }

        with self.jobs_lock:
            self.jobs[job_id] = job

        worker = threading.Thread(
            target=self._run_audiosr_job,
            args=(job_id,),
            daemon=True,
        )
        worker.start()

        return {
            "ok": True,
            "job_id": job_id,
            "job": self._snapshot_job(job_id),
        }

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        job_id = (job_id or "").strip()

        with self.jobs_lock:
            if job_id not in self.jobs:
                return {
                    "ok": False,
                    "error": f"Job inconnu : {job_id}",
                }

        return {
            "ok": True,
            "job": self._snapshot_job(job_id),
        }

    def start_audio_analysis(
        self,
        project_key: str,
        processed_wav: str,
        analysis_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Démarre un job d'analyse comparative :
        référence originale vs WAV traité.
        """
        analysis_context = analysis_context or {}
        project_key = (project_key or "").strip()
        processed_wav = (processed_wav or "").strip()

        if not project_key:
            return {
                "ok": False,
                "error": "Clé de projet manquante.",
            }

        if not processed_wav:
            return {
                "ok": False,
                "error": "Chemin du fichier traité manquant.",
            }

        try:
            project_payload, project_json_path = self._load_project(project_key)
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

        original_wav = Path(project_payload["paths"]["reference_wav"])
        processed_wav_path = Path(processed_wav)

        if not original_wav.exists():
            return {
                "ok": False,
                "error": f"Référence WAV introuvable : {original_wav}",
            }

        if not processed_wav_path.exists():
            return {
                "ok": False,
                "error": f"Fichier traité introuvable : {processed_wav_path}",
            }

        job_id = uuid.uuid4().hex[:12]
        created_at = datetime.now().isoformat(timespec="seconds")

        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        analysis_dir = Path(project_payload["paths"]["project_dir"]) / "analysis"
        run_dir = analysis_dir / f"comparison_{run_stamp}_{job_id[:6]}"

        run_dir.mkdir(parents=True, exist_ok=True)

        job = {
            "id": job_id,
            "kind": "audio_analysis",
            "status": "queued",
            "created_at": created_at,
            "started_at": None,
            "finished_at": None,
            "project_key": project_key,
            "project_json_path": str(project_json_path),
            "original_wav": str(original_wav),
            "processed_wav": str(processed_wav_path),
            "run_dir": str(run_dir),
            "analysis_context": {
                "label": str(analysis_context.get("label", "AudioSR")),
                "chunk_size_s": analysis_context.get("chunk_size_s"),
                "chunk_overlap_fraction": analysis_context.get("chunk_overlap_fraction"),
            },
            "progress": {
                "done": 0,
                "total": 0,
                "percent": 0.0,
            },
            "logs": [
                "Job d’analyse comparative créé.",
                f"Projet : {project_key}",
            ],
            "result": None,
            "error": None,
        }

        with self.jobs_lock:
            self.jobs[job_id] = job

        worker = threading.Thread(
            target=self._run_audio_analysis_job,
            args=(job_id,),
            daemon=True,
        )
        worker.start()

        return {
            "ok": True,
            "job_id": job_id,
            "job": self._snapshot_job(job_id),
        }

    def _run_audio_analysis_job(self, job_id: str) -> None:
        """
        Fonction exécutée dans un thread séparé.
        """
        self._update_job(
            job_id,
            status="running",
            started_at=datetime.now().isoformat(timespec="seconds"),
        )
        self._append_job_log(job_id, "Démarrage de l’analyse comparative.")

        try:
            job = self._snapshot_job(job_id)

            result = run_audio_analysis(
                original_wav=Path(job["original_wav"]),
                processed_wav=Path(job["processed_wav"]),
                output_dir=Path(job["run_dir"]),
                chunk_size_s=job["analysis_context"].get("chunk_size_s"),
                chunk_overlap_fraction=job["analysis_context"].get(
                    "chunk_overlap_fraction"
                ),
                label=job["analysis_context"].get("label", "AudioSR"),
                log=lambda message: self._append_job_log(job_id, message),
                progress=lambda done, total: self._update_job_progress(
                    job_id,
                    done,
                    total,
                ),
            )

            result_payload = {
                **result,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }

            self._update_job(
                job_id,
                status="done",
                finished_at=result_payload["finished_at"],
                result=result_payload,
            )

            self._append_job_log(job_id, "Analyse comparative terminée avec succès.")

            self._append_analysis_run_to_project(
                job_id=job_id,
                result_payload=result_payload,
            )

        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"

            self._update_job(
                job_id,
                status="error",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                error=error_message,
            )

            self._append_job_log(job_id, "ÉCHEC DE L’ANALYSE COMPARATIVE.")
            self._append_job_log(job_id, error_message)

            tb = traceback.format_exc()
            for line in tb.splitlines():
                self._append_job_log(job_id, line)

    def _run_audiosr_job(self, job_id: str) -> None:
        """
        Fonction exécutée dans un thread séparé.
        """
        self._update_job(
            job_id,
            status="running",
            started_at=datetime.now().isoformat(timespec="seconds"),
        )
        self._append_job_log(job_id, "Démarrage du traitement AudioSR.")

        try:
            job = self._snapshot_job(job_id)

            input_wav = Path(job["input_wav"])
            output_wav = Path(job["output_wav"])
            settings = job["settings"]

            result = run_audiosr_upscale(
                input_wav=input_wav,
                output_wav=output_wav,
                settings=settings,
                log=lambda message: self._append_job_log(job_id, message),
                progress=lambda done, total: self._update_job_progress(
                    job_id,
                    done,
                    total,
                ),
            )

            output_probe = ffprobe_audio(output_wav)

            result_payload = {
                **result,
                "output_probe": output_probe,
                "finished_at": datetime.now().isoformat(timespec="seconds"),
            }

            self._update_job(
                job_id,
                status="done",
                finished_at=result_payload["finished_at"],
                result=result_payload,
            )

            self._append_job_log(job_id, "Traitement AudioSR terminé avec succès.")

            self._append_upscale_run_to_project(
                job_id=job_id,
                result_payload=result_payload,
            )

        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"

            self._update_job(
                job_id,
                status="error",
                finished_at=datetime.now().isoformat(timespec="seconds"),
                error=error_message,
            )

            self._append_job_log(job_id, "ÉCHEC DU TRAITEMENT AUDIOSR.")
            self._append_job_log(job_id, error_message)

            # Très utile au développement : le traceback complet reste dans les logs du job.
            tb = traceback.format_exc()
            for line in tb.splitlines():
                self._append_job_log(job_id, line)

    def _normalize_audiosr_settings(
        self,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Définit les valeurs par défaut de la V2.
        """
        return {
            "model_name": str(settings.get("model_name", "basic")),
            "device": str(settings.get("device", "cuda:0")),
            "chunk_size": float(settings.get("chunk_size", 5.12)),
            "overlap": float(settings.get("overlap", 0.04)),
            "ddim_steps": int(settings.get("ddim_steps", 50)),
            "guidance_scale": float(settings.get("guidance_scale", 3.5)),
            "seed": int(settings.get("seed", 0)),
            "multiband_ensemble": bool(settings.get("multiband_ensemble", False)),
            "input_cutoff": int(settings.get("input_cutoff", 12000)),
        }

    # ========================================================
    # PROJETS
    # ========================================================

    def _load_project(
        self,
        project_key: str,
    ) -> tuple[dict[str, Any], Path]:
        project_dir = (
            self.base_dir
            / "workspace"
            / "projects"
            / project_key
        )

        project_json_path = project_dir / "project.json"

        if not project_json_path.exists():
            raise RuntimeError(
                f"Fichier projet introuvable : {project_json_path}"
            )

        with project_json_path.open("r", encoding="utf-8") as file:
            project_payload = json.load(file)

        return project_payload, project_json_path

    def _append_upscale_run_to_project(
        self,
        job_id: str,
        result_payload: dict[str, Any],
    ) -> None:
        job = self._snapshot_job(job_id)
        project_key = job["project_key"]

        project_payload, project_json_path = self._load_project(project_key)

        project_payload.setdefault("upscale_runs", [])

        project_payload["upscale_runs"].append(
            {
                "job_id": job_id,
                "created_at": job["created_at"],
                "started_at": job["started_at"],
                "finished_at": job["finished_at"],
                "status": job["status"],
                "settings": job["settings"],
                "paths": {
                    "run_dir": job["run_dir"],
                    "output_wav": job["output_wav"],
                },
                "technical_info": {
                    "output_probe": result_payload["output_probe"],
                },
            }
        )

        with project_json_path.open("w", encoding="utf-8") as file:
            json.dump(
                project_payload,
                file,
                ensure_ascii=False,
                indent=2,
            )

    def _append_analysis_run_to_project(
        self,
        job_id: str,
        result_payload: dict[str, Any],
    ) -> None:
        job = self._snapshot_job(job_id)
        project_key = job["project_key"]

        project_payload, project_json_path = self._load_project(project_key)

        project_payload.setdefault("analysis_runs", [])

        project_payload["analysis_runs"].append(
            {
                "job_id": job_id,
                "created_at": job["created_at"],
                "started_at": job["started_at"],
                "finished_at": job["finished_at"],
                "status": job["status"],
                "paths": {
                    "run_dir": job["run_dir"],
                    "report_json": result_payload["summary"]["report_json"],
                    "difference_full_wav": result_payload["summary"][
                        "difference_full_wav"
                    ],
                    "difference_highfreq_wav": result_payload["summary"][
                        "difference_highfreq_wav"
                    ],
                },
                "summary": result_payload["summary"],
            }
        )

        with project_json_path.open("w", encoding="utf-8") as file:
            json.dump(
                project_payload,
                file,
                ensure_ascii=False,
                indent=2,
            )

    # ========================================================
    # GESTION DE JOBS
    # ========================================================

    def _snapshot_job(self, job_id: str) -> dict[str, Any]:
        with self.jobs_lock:
            job = self.jobs.get(job_id)

            if job is None:
                raise RuntimeError(f"Job inconnu : {job_id}")

            return deepcopy(job)

    def _update_job(
        self,
        job_id: str,
        **updates: Any,
    ) -> None:
        with self.jobs_lock:
            if job_id not in self.jobs:
                return

            self.jobs[job_id].update(updates)

    def _append_job_log(
        self,
        job_id: str,
        message: str,
    ) -> None:
        with self.jobs_lock:
            if job_id not in self.jobs:
                return

            self.jobs[job_id]["logs"].append(str(message))

    def _update_job_progress(
        self,
        job_id: str,
        done: int,
        total: int,
    ) -> None:
        percent = 0.0

        if total > 0:
            percent = round((done / total) * 100.0, 2)

        with self.jobs_lock:
            if job_id not in self.jobs:
                return

            self.jobs[job_id]["progress"] = {
                "done": int(done),
                "total": int(total),
                "percent": percent,
            }

    # ========================================================
    # OUVERTURE DOSSIERS
    # ========================================================

    def open_path(self, path: str) -> dict[str, Any]:
        target = Path(path)

        if not target.exists():
            return {
                "ok": False,
                "error": f"Chemin introuvable : {target}",
            }

        try:
            os.startfile(str(target))
            return {"ok": True}
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
            }