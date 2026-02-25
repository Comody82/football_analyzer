"""Gestione clip e assemblaggio highlights."""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ClipSegment:
    """Segmento video da ritagliare."""
    start_ms: int
    end_ms: int
    label: str
    event_type: str


class ClipManager:
    """Crea clip e assembla video highlights."""

    def __init__(self, highlights_folder: str = "Highlights"):
        self.highlights_folder = Path(highlights_folder)
        self.highlights_folder.mkdir(exist_ok=True)
        self._ffmpeg_available: Optional[bool] = None

    def _check_ffmpeg(self) -> bool:
        if self._ffmpeg_available is not None:
            return self._ffmpeg_available
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            self._ffmpeg_available = True
        except FileNotFoundError:
            self._ffmpeg_available = False
        return self._ffmpeg_available

    def create_clip(
        self,
        source_path: str,
        event_timestamp_ms: int,
        pre_seconds: float,
        post_seconds: float,
        output_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Ritaglia un clip centrato sull'evento.
        Ritorna il path del file creato o None in caso di errore.
        """
        if not self._check_ffmpeg():
            return None

        source = Path(source_path)
        if not source.exists():
            return None

        start_sec = max(0, (event_timestamp_ms / 1000) - pre_seconds)
        duration_sec = pre_seconds + post_seconds

        base_name = output_name or f"clip_{event_timestamp_ms}"
        out_path = self.highlights_folder / f"{base_name}.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(source),
            "-t", str(duration_sec),
            "-c", "copy",
            "-avoid_negative_ts", "1",
            str(out_path)
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                timeout=60
            )
            return str(out_path) if out_path.exists() else None
        except Exception:
            return None

    def create_clip_range(
        self,
        source_path: str,
        start_ms: int,
        end_ms: int,
        output_name: Optional[str] = None
    ) -> Optional[str]:
        """Crea un clip con inizio e fine personalizzati (tempistica in millisecondi)."""
        if not self._check_ffmpeg():
            return None
        source = Path(source_path)
        if not source.exists():
            return None
        start_sec = max(0, start_ms / 1000)
        duration_sec = max(0.1, (end_ms - start_ms) / 1000)
        base_name = output_name or f"clip_{start_ms}_{end_ms}"
        out_path = self.highlights_folder / f"{base_name}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(source),
            "-t", str(duration_sec),
            "-c", "copy",
            "-avoid_negative_ts", "1",
            str(out_path)
        ]
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                timeout=60
            )
            return str(out_path) if out_path.exists() else None
        except Exception:
            return None

    def create_clips_from_events(
        self,
        source_path: str,
        events: List[Tuple[int, str]],  # [(timestamp_ms, label), ...]
        pre_seconds: float,
        post_seconds: float
    ) -> List[str]:
        """Crea clip per ogni evento e ritorna la lista dei path."""
        created = []
        for i, (ts_ms, label) in enumerate(events):
            safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:30]
            name = f"clip_{i+1:03d}_{safe_label}_{ts_ms}"
            path = self.create_clip(source_path, ts_ms, pre_seconds, post_seconds, name)
            if path:
                created.append(path)
        return created

    def assemble_highlights(
        self,
        clip_paths: List[str],
        output_name: str = "highlights_assembled"
    ) -> Optional[str]:
        """
        Assembla più clip in un unico video.
        Usa concat demuxer di FFmpeg.
        """
        if not self._check_ffmpeg() or not clip_paths:
            return None

        out_path = self.highlights_folder / f"{output_name}.mp4"

        # Crea file list per concat
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            for p in clip_paths:
                p_abs = str(Path(p).resolve()).replace("\\", "/")
                f.write(f"file '{p_abs}'\n")
            list_path = f.name

        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                str(out_path)
            ]
            subprocess.run(
                cmd,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                timeout=300
            )
            return str(out_path) if out_path.exists() else None
        except Exception:
            return None
        finally:
            try:
                os.unlink(list_path)
            except OSError:
                pass

    def is_available(self) -> bool:
        return self._check_ffmpeg()
