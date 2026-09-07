"""Attachment storage.

Files land on local disk under ``settings.media_root`` and are served back as
static assets. Everything storage-specific is confined to this module, so
swapping in S3/R2/GCS means reimplementing ``store_upload`` and ``public_url``
and touching nothing else.
"""

from __future__ import annotations

import mimetypes
import re
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import Unprocessable, ValidationError

# Deliberately an allowlist, not a denylist: anything not named here is refused.
IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
}
FILE_TYPES = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/csv": ".csv",
    "text/markdown": ".md",
    "application/json": ".json",
    "application/zip": ".zip",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/webm": ".weba",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
ALLOWED_TYPES = {**IMAGE_TYPES, **FILE_TYPES}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def media_dir() -> Path:
    path = Path(settings.media_root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_url(stored_name: str) -> str:
    return f"{settings.media_url_prefix}/{stored_name}"


def is_image(mime_type: str | None) -> bool:
    return (mime_type or "") in IMAGE_TYPES


def safe_display_name(name: str | None) -> str:
    cleaned = _SAFE_NAME.sub("_", (name or "file").strip())[:120]
    return cleaned or "file"


async def store_upload(upload: UploadFile) -> dict[str, object]:
    """Validate and persist one upload. Returns attachment metadata."""
    mime_type = (upload.content_type or "").split(";")[0].strip().lower()
    if mime_type not in ALLOWED_TYPES:
        raise Unprocessable(
            f"Unsupported file type: {mime_type or 'unknown'}",
            code="UNSUPPORTED_MEDIA_TYPE",
        )

    # Read in chunks so a huge upload is rejected without buffering all of it.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise ValidationError(
                f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)}MB limit",
                code="FILE_TOO_LARGE",
            )
        chunks.append(chunk)

    if total == 0:
        raise ValidationError("File is empty")

    original = safe_display_name(upload.filename)
    extension = (
        Path(original).suffix.lower()
        if Path(original).suffix.lower() == ALLOWED_TYPES[mime_type]
        else ALLOWED_TYPES[mime_type]
    )
    # Random stored name: the client's filename never touches the filesystem.
    stored_name = f"{uuid.uuid4().hex}{extension}"
    destination = media_dir() / stored_name
    destination.write_bytes(b"".join(chunks))

    return {
        "url": public_url(stored_name),
        "mime_type": mime_type,
        "size_bytes": total,
        "name": original,
        "kind": "image" if is_image(mime_type) else "file",
    }


def guess_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
