"""
Browser-friendly audio preview for Admin UI /api/assets/preview.

Telegram voice is typically Ogg + Opus (.oga). Many browsers (notably Safari/WebKit)
do not decode Opus-in-Ogg in <audio>. STT still uses original bytes; this module only
produces an optional MP3 sidecar under the asset storage root for preview.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path


def needs_browser_mp3_preview(path: Path, media_type: str) -> bool:
    """True if we should try MP3 transcode for HTML5 playback."""
    suf = path.suffix.lower()
    mt = (media_type or "").lower()
    if suf == ".oga":
        return True
    if mt != "audio/ogg" and suf != ".ogg":
        return False
    try:
        head = path.read_bytes()[:16384]
    except OSError:
        return False
    if not head.startswith(b"OggS"):
        return False
    return b"OpusHead" in head


def ensure_mp3_browser_preview(
    src: Path,
    *,
    cache_root: Path,
    timeout_sec: int = 120,
) -> Path | None:
    """
    Return path to cached MP3 derived from src, or None if ffmpeg missing/failed.

    Cache path: <cache_root>/.browser_audio_preview/<sha256>.mp3
    """
    if shutil.which("ffmpeg") is None:
        return None
    try:
        payload = src.read_bytes()
    except OSError:
        return None
    if not payload:
        return None
    digest = hashlib.sha256(payload).hexdigest()
    cache_dir = cache_root / ".browser_audio_preview"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    out = cache_dir / f"{digest}.mp3"
    if out.is_file() and out.stat().st_size > 0:
        return out
    tmp = cache_dir / f".{digest}.mp3.part"
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src),
                "-vn",
                "-acodec",
                "libmp3lame",
                "-q:a",
                "6",
                str(tmp),
            ],
            check=False,
            timeout=timeout_sec,
            capture_output=True,
        )
        if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size == 0:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            return None
        tmp.replace(out)
        return out
    except (subprocess.TimeoutExpired, OSError):
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return None
