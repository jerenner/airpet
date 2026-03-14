from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ARTIFACT_STORE_SCHEMA_VERSION = "2026-03-14.multimodal-intake.checkpoint1"

_ALLOWED_MIME_TO_EXTENSION = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}


class AIArtifactValidationError(ValueError):
    """Raised when artifact intake/listing inputs are invalid."""


class AIArtifactStore:
    """Persist and query multimodal intake artifacts for AI planning workflows."""

    def __init__(self, base_dir: Path | str, workspace_root: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir)
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()
        self.blobs_dir = self.base_dir / "blobs"
        self.manifest_path = self.base_dir / "manifest.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.blobs_dir.mkdir(parents=True, exist_ok=True)

    def ingest_upload(
        self,
        file_storage: Any,
        *,
        source_path: Optional[str] = None,
        source_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        filename = (getattr(file_storage, "filename", None) or "").strip()
        if not filename:
            raise AIArtifactValidationError("Missing filename for uploaded artifact.")

        payload = file_storage.read()
        if not payload:
            raise AIArtifactValidationError("Uploaded artifact is empty.")

        mime_type = self._resolve_allowed_mime_type(
            uploaded_mime=(getattr(file_storage, "mimetype", None) or ""),
            filename=filename,
        )

        sha256 = hashlib.sha256(payload).hexdigest()
        now = datetime.now(timezone.utc)
        created_at = _iso_utc(now)
        artifact_id = self._build_artifact_id(now, sha256)
        extension = _ALLOWED_MIME_TO_EXTENSION[mime_type]
        safe_stem = _sanitize_stem(Path(filename).stem)
        stored_filename = f"{artifact_id}_{safe_stem}{extension}"

        blob_path = self.blobs_dir / stored_filename
        blob_path.write_bytes(payload)

        provenance = self._normalize_source_path(source_path)

        entry: Dict[str, Any] = {
            "artifact_id": artifact_id,
            "schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
            "mime_type": mime_type,
            "size_bytes": len(payload),
            "sha256": sha256,
            "original_filename": filename,
            "stored_filename": stored_filename,
            "created_at": created_at,
            "updated_at": created_at,
            "source_label": (source_label or "").strip() or None,
            **provenance,
        }

        manifest = self._load_manifest()
        manifest["artifacts"].append(entry)
        self._write_manifest(manifest)
        return dict(entry)

    def list_metadata(self, *, limit: int = 50, include_missing_files: bool = False) -> List[Dict[str, Any]]:
        if not isinstance(limit, int) or limit < 0:
            raise AIArtifactValidationError("limit must be a non-negative integer.")

        manifest = self._load_manifest()
        artifacts = list(manifest["artifacts"])

        artifacts.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("artifact_id") or ""),
            ),
            reverse=True,
        )

        if not include_missing_files:
            artifacts = [item for item in artifacts if (self.blobs_dir / str(item.get("stored_filename") or "")).is_file()]

        if limit == 0:
            return []
        return [dict(item) for item in artifacts[:limit]]

    def get_metadata(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        artifact_id = (artifact_id or "").strip()
        if not artifact_id:
            raise AIArtifactValidationError("artifact_id must be a non-empty string.")

        manifest = self._load_manifest()
        for item in manifest["artifacts"]:
            if item.get("artifact_id") == artifact_id:
                return dict(item)
        return None

    def resolve_artifact_path(self, artifact_id: str) -> Optional[Path]:
        metadata = self.get_metadata(artifact_id)
        if not metadata:
            return None
        candidate = self.blobs_dir / str(metadata.get("stored_filename") or "")
        return candidate if candidate.is_file() else None

    def _resolve_allowed_mime_type(self, *, uploaded_mime: str, filename: str) -> str:
        mime_type = (uploaded_mime or "").split(";")[0].strip().lower()
        if mime_type in _ALLOWED_MIME_TO_EXTENSION:
            return mime_type

        guessed_mime, _ = mimetypes.guess_type(filename)
        guessed_mime = (guessed_mime or "").strip().lower()
        if guessed_mime in _ALLOWED_MIME_TO_EXTENSION:
            return guessed_mime

        raise AIArtifactValidationError(
            "Unsupported artifact type. Only PDF, PNG, JPEG, and WEBP uploads are accepted."
        )

    def _build_artifact_id(self, now: datetime, sha256: str) -> str:
        ts = now.strftime("%Y%m%dT%H%M%S%fZ")
        base = f"artifact_{ts}_{sha256[:12]}"

        manifest = self._load_manifest()
        existing_ids = {str(item.get("artifact_id") or "") for item in manifest["artifacts"]}

        if base not in existing_ids:
            return base

        suffix = 2
        while True:
            candidate = f"{base}_{suffix}"
            if candidate not in existing_ids:
                return candidate
            suffix += 1

    def _normalize_source_path(self, source_path: Optional[str]) -> Dict[str, Any]:
        raw = (source_path or "").strip()
        if not raw:
            return {
                "source_path_input": None,
                "source_path_resolved": None,
                "source_path_exists": False,
                "source_path_is_file": False,
                "source_path_within_workspace": False,
            }

        path_obj = Path(raw).expanduser()
        if not path_obj.is_absolute():
            path_obj = (self.workspace_root / path_obj)

        resolved = path_obj.resolve()
        exists = resolved.exists()
        is_file = resolved.is_file()

        within_workspace = False
        try:
            resolved.relative_to(self.workspace_root)
            within_workspace = True
        except Exception:
            within_workspace = False

        return {
            "source_path_input": raw,
            "source_path_resolved": str(resolved),
            "source_path_exists": bool(exists),
            "source_path_is_file": bool(is_file),
            "source_path_within_workspace": bool(within_workspace),
        }

    def _load_manifest(self) -> Dict[str, Any]:
        if not self.manifest_path.exists():
            return {
                "schema_version": ARTIFACT_STORE_SCHEMA_VERSION,
                "artifacts": [],
            }

        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Artifact manifest is not valid JSON: {exc}") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Artifact manifest must be a JSON object.")

        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise RuntimeError("Artifact manifest missing 'artifacts' list.")

        return {
            "schema_version": str(payload.get("schema_version") or ARTIFACT_STORE_SCHEMA_VERSION),
            "artifacts": artifacts,
        }

    def _write_manifest(self, payload: Dict[str, Any]) -> None:
        payload = {
            "schema_version": str(payload.get("schema_version") or ARTIFACT_STORE_SCHEMA_VERSION),
            "artifacts": list(payload.get("artifacts") or []),
        }
        tmp_path = self.manifest_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.manifest_path)


def _sanitize_stem(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem or "")
    cleaned = cleaned.strip("._-")
    return cleaned or "artifact"


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
