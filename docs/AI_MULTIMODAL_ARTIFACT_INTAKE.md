# AI Multimodal Artifact Intake Contract (Checkpoint 1)

Schema version: `2026-03-14.multimodal-intake.checkpoint1`

This checkpoint introduces deterministic PDF/image artifact intake for AI planning workflows.

## Endpoints

### `POST /api/ai/artifacts/upload`
Multipart upload endpoint for AI-planning artifacts.

Accepted file field names:
- `artifact` (preferred)
- `file` (alias)

Optional form fields:
- `source_path` (original local/source path for provenance checks)
- `source_label` (free-form source tag)

Accepted MIME classes:
- `application/pdf`
- `image/png`
- `image/jpeg`
- `image/webp`

Response shape:
```json
{
  "success": true,
  "schema_version": "2026-03-14.multimodal-intake.checkpoint1",
  "artifact": {
    "artifact_id": "artifact_...",
    "mime_type": "application/pdf",
    "size_bytes": 12345,
    "sha256": "...",
    "original_filename": "detector_sketch.pdf",
    "stored_filename": "artifact_..._detector_sketch.pdf",
    "created_at": "2026-03-14T12:34:56.789Z",
    "updated_at": "2026-03-14T12:34:56.789Z",
    "source_label": "user-dropbox",
    "source_path_input": "/path/origin.pdf",
    "source_path_resolved": "/path/origin.pdf",
    "source_path_exists": true,
    "source_path_is_file": true,
    "source_path_within_workspace": false
  }
}
```

### `GET|POST /api/ai/artifacts/list`
Deterministic artifact listing.

Inputs:
- `limit` (non-negative integer, default `50`)
- `include_missing_files` (boolean, default `false`)

Behavior:
- sorted by `(created_at DESC, artifact_id DESC)`
- when `include_missing_files=false`, metadata entries with missing blob files are filtered out

### `GET /api/ai/artifacts/<artifact_id>`
Fetch deterministic metadata for one artifact id.

## Persistence Layout

Per-session artifact store under project directory:
- `<projects_dir>/.airpet_ai_artifacts/manifest.json`
- `<projects_dir>/.airpet_ai_artifacts/blobs/*`

Manifest stores normalized metadata/provenance for reproducible downstream extraction/planning steps.
