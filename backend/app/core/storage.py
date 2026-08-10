"""
Storage utilities.

Supports:
- Local filesystem storage
- S3-compatible object storage

The storage layer intentionally hides backend-specific details
from API and business logic.
"""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings


# ==========================================================
# Local Storage
# ==========================================================


def ensure_upload_dir() -> str:
    """Ensure that the local upload directory exists."""

    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)

    return upload_dir


def _local_path(object_key: str) -> Path:
    """
    Resolve an object key to a local storage path.

    Prevents path traversal outside the configured upload directory.
    """

    upload_dir = Path(ensure_upload_dir()).resolve()

    # Normalize object key separators for local filesystem.
    normalized_key = object_key.replace("\\", "/").lstrip("/")

    path = (upload_dir / normalized_key).resolve()

    try:
        path.relative_to(upload_dir)
    except ValueError as exc:
        raise ValueError("Invalid storage object key") from exc

    return path


# ==========================================================
# S3 Client
# ==========================================================


def _get_s3_client():
    """Create an S3/S3-compatible client."""

    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


# ==========================================================
# Upload
# ==========================================================


def upload_file_object(
    object_key: str,
    contents: bytes,
    content_type: str,
) -> str:
    """
    Upload file contents to the configured storage backend.

    Returns:
        Storage object key for S3.
        Absolute filesystem path for local storage.
    """

    if not object_key:
        raise ValueError("Storage object key is required")

    if not contents:
        raise ValueError("File contents cannot be empty")

    # ------------------------------------------------------
    # S3
    # ------------------------------------------------------

    if settings.aws_s3_bucket:
        client = _get_s3_client()

        try:
            client.put_object(
                Bucket=settings.aws_s3_bucket,
                Key=object_key,
                Body=contents,
                ContentType=content_type,
            )
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError(
                "Failed to upload file to S3"
            ) from exc

        return object_key

    # ------------------------------------------------------
    # Local filesystem
    # ------------------------------------------------------

    path = _local_path(object_key)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        path.write_bytes(contents)
    except OSError as exc:
        raise RuntimeError(
            "Failed to write file to local storage"
        ) from exc

    return object_key


# ==========================================================
# Delete
# ==========================================================


def delete_file(object_key: str) -> None:
    """
    Delete a file from the configured storage backend.

    This function is intentionally idempotent:
    deleting an object that does not exist does not raise an error.
    """

    if not object_key:
        return

    # ------------------------------------------------------
    # S3
    # ------------------------------------------------------

    if settings.aws_s3_bucket:
        client = _get_s3_client()

        try:
            client.delete_object(
                Bucket=settings.aws_s3_bucket,
                Key=object_key,
            )
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError(
                "Failed to delete file from S3"
            ) from exc

        return

    # ------------------------------------------------------
    # Local filesystem
    # ------------------------------------------------------

    path = _local_path(object_key)

    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(
            "Failed to delete file from local storage"
        ) from exc


# ==========================================================
# Download URL
# ==========================================================


def get_download_url(object_key: str) -> str:
    """
    Generate a download URL for an object.

    For S3:
        Returns a presigned URL.

    For local storage:
        Returns the storage path.

    Note:
        Local storage should eventually be served through a
        dedicated authenticated download endpoint rather than
        exposing filesystem paths directly.
    """

    if not object_key:
        raise ValueError("Storage object key is required")

    # ------------------------------------------------------
    # S3
    # ------------------------------------------------------

    if settings.aws_s3_bucket:
        client = _get_s3_client()

        try:
            return client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": settings.aws_s3_bucket,
                    "Key": object_key,
                },
                ExpiresIn=settings.s3_signed_url_expire_seconds,
            )
        except (ClientError, BotoCoreError) as exc:
            raise RuntimeError(
                "Failed to generate download URL"
            ) from exc

    # ------------------------------------------------------
    # Local filesystem
    # ------------------------------------------------------

    path = _local_path(object_key)

    if not path.exists():
        raise FileNotFoundError(
            "Stored file does not exist"
        )

    return object_key