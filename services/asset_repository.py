"""Storage abstraction for generated assets and files (filesystem backend)."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_SAFE_NAME_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_NS_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_/-]+")


class AssetRepositoryError(RuntimeError):
    """Base class for storage abstraction errors."""


class AssetValidationError(AssetRepositoryError):
    """Raised when input params are malformed or unsafe."""


class AssetNotFoundError(AssetRepositoryError):
    """Raised when requested asset does not exist."""


@dataclass(frozen=True)
class AssetRef:
    """Stable reference to an asset managed by repository."""

    backend: str
    namespace: str
    relative_path: str
    filename: str
    sha256: str
    size_bytes: int
    content_type: str


class AssetRepository(ABC):
    """Abstract storage API for binary assets."""

    @abstractmethod
    def save_bytes(
        self,
        data: bytes,
        *,
        namespace: str,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> AssetRef:
        raise NotImplementedError

    @abstractmethod
    def save_file(
        self,
        source_path: str | Path,
        *,
        namespace: str,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> AssetRef:
        raise NotImplementedError

    @abstractmethod
    def exists(self, ref_or_rel_path: AssetRef | str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, ref_or_rel_path: AssetRef | str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def resolve_path(self, ref_or_rel_path: AssetRef | str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def delete(self, ref_or_rel_path: AssetRef | str) -> None:
        raise NotImplementedError


class FilesystemAssetRepository(AssetRepository):
    """
    Filesystem-backed asset repository.

    Deterministic layout:
      <base>/<namespace>/<sha_prefix_2>/<sha_prefix_4>/<sha256>_<safe_filename>
    """

    backend_name: Final[str] = "filesystem"

    def __init__(self, base_dir: str | Path) -> None:
        root = Path(base_dir)
        if not root.is_absolute():
            root = root.resolve()
        self._base_dir = root
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def save_bytes(
        self,
        data: bytes,
        *,
        namespace: str,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> AssetRef:
        if not isinstance(data, (bytes, bytearray)):
            raise AssetValidationError("save_bytes expects bytes-like payload")
        raw = bytes(data)
        if len(raw) == 0:
            raise AssetValidationError("empty payload is not allowed")
        safe_ns = self._sanitize_namespace(namespace)
        digest = hashlib.sha256(raw).hexdigest()
        safe_name = self._normalize_filename(filename, content_type, fallback_digest=digest)
        rel = Path(safe_ns) / digest[:2] / digest[2:4] / f"{digest}_{safe_name}"
        abs_path = self._safe_join(rel)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(raw)
        ctype = self._detect_content_type(safe_name, content_type)
        return AssetRef(
            backend=self.backend_name,
            namespace=safe_ns,
            relative_path=str(rel.as_posix()),
            filename=safe_name,
            sha256=digest,
            size_bytes=len(raw),
            content_type=ctype,
        )

    def save_file(
        self,
        source_path: str | Path,
        *,
        namespace: str,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> AssetRef:
        src = Path(source_path)
        if not src.is_file():
            raise AssetNotFoundError(f"source file not found: {src}")
        src_name = filename or src.name
        payload = src.read_bytes()
        return self.save_bytes(
            payload,
            namespace=namespace,
            filename=src_name,
            content_type=content_type,
        )

    def exists(self, ref_or_rel_path: AssetRef | str) -> bool:
        p = self.resolve_path(ref_or_rel_path)
        return p.is_file()

    def read_bytes(self, ref_or_rel_path: AssetRef | str) -> bytes:
        p = self.resolve_path(ref_or_rel_path)
        if not p.is_file():
            raise AssetNotFoundError(f"asset does not exist: {p}")
        return p.read_bytes()

    def resolve_path(self, ref_or_rel_path: AssetRef | str) -> Path:
        rel = (
            Path(ref_or_rel_path.relative_path)
            if isinstance(ref_or_rel_path, AssetRef)
            else Path(str(ref_or_rel_path))
        )
        return self._safe_join(rel)

    def delete(self, ref_or_rel_path: AssetRef | str) -> None:
        p = self.resolve_path(ref_or_rel_path)
        if p.exists() and p.is_file():
            p.unlink()
            self._cleanup_empty_parents(p.parent)

    def _sanitize_namespace(self, namespace: str) -> str:
        ns = (namespace or "").strip().replace("\\", "/")
        ns = _SAFE_NS_RE.sub("-", ns).strip("/")
        if not ns:
            raise AssetValidationError("namespace is empty")
        parts = [x for x in ns.split("/") if x and x not in (".", "..")]
        if not parts:
            raise AssetValidationError("namespace is invalid")
        return "/".join(parts)

    def _normalize_filename(
        self,
        filename: str | None,
        content_type: str | None,
        *,
        fallback_digest: str,
    ) -> str:
        candidate = (filename or "").strip()
        if candidate:
            candidate = Path(candidate).name
        if not candidate:
            ext = self._extension_from_content_type(content_type)
            candidate = f"asset{ext}"
        stem = Path(candidate).stem or f"asset-{fallback_digest[:8]}"
        ext = Path(candidate).suffix.lower()
        safe_stem = _SAFE_NAME_RE.sub("-", stem).strip(".-_")
        if not safe_stem:
            safe_stem = f"asset-{fallback_digest[:8]}"
        safe_ext = _SAFE_NAME_RE.sub("", ext)
        if safe_ext and not safe_ext.startswith("."):
            safe_ext = "." + safe_ext
        return f"{safe_stem}{safe_ext}"

    def _detect_content_type(self, filename: str, explicit: str | None) -> str:
        if explicit and explicit.strip():
            return explicit.strip().lower()
        guessed, _enc = mimetypes.guess_type(filename)
        return (guessed or "application/octet-stream").lower()

    def _extension_from_content_type(self, content_type: str | None) -> str:
        if not content_type:
            return ".bin"
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip().lower())
        return ext or ".bin"

    def _safe_join(self, rel: Path) -> Path:
        if rel.is_absolute():
            raise AssetValidationError("absolute paths are not allowed")
        rel_posix = str(rel.as_posix())
        if ".." in rel.parts:
            raise AssetValidationError("path traversal is not allowed")
        if rel_posix.startswith("/"):
            raise AssetValidationError("invalid relative path")
        resolved = (self._base_dir / rel).resolve()
        try:
            resolved.relative_to(self._base_dir.resolve())
        except ValueError as exc:
            raise AssetValidationError("path escapes storage root") from exc
        return resolved

    def _cleanup_empty_parents(self, start: Path) -> None:
        cur = start
        root = self._base_dir.resolve()
        while True:
            if cur == root:
                return
            try:
                cur.rmdir()
            except OSError:
                return
            cur = cur.parent
