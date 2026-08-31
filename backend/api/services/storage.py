"""S3 storage for character images.

Uploads raw image bytes to the configured AWS S3 bucket and returns a public URL. Credentials
come from settings (env-driven). While any required value is blank or still a REPLACE_ME
placeholder, `is_configured()` is False and callers should surface a "not configured" message
rather than attempting a doomed upload.
"""
from __future__ import annotations

import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings


class StorageNotConfigured(Exception):
    """AWS S3 credentials/bucket are not set up yet."""


class StorageError(Exception):
    """The upload itself failed (network, permissions, etc.)."""


_PLACEHOLDER = "REPLACE_ME"

_EXT_BY_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _is_set(value: str) -> bool:
    return bool(value) and _PLACEHOLDER not in value


def is_configured() -> bool:
    """True only when real (non-placeholder) AWS credentials + bucket are present."""
    return all(
        _is_set(v)
        for v in (
            settings.AWS_ACCESS_KEY_ID,
            settings.AWS_SECRET_ACCESS_KEY,
            settings.AWS_S3_BUCKET,
        )
    )


def _client():
    # Pin the *regional* endpoint + virtual-hosted addressing so presigned URLs point straight at
    # `<bucket>.s3.<region>.amazonaws.com`. The default global endpoint (`s3.amazonaws.com`) makes
    # S3 answer buckets outside us-east-1 with a 307 redirect to a different host, which invalidates
    # the SigV4 signature (403). Signing with the regional host avoids the redirect entirely.
    region = settings.AWS_REGION
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


def _public_url(key: str) -> str:
    base = settings.AWS_S3_PUBLIC_BASE_URL
    if base:
        return f"{base.rstrip('/')}/{key}"
    return f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"


def view_url(key: str, *, expires_in: int = 3600) -> str:
    """A URL the browser can load for a stored object `key`.

    - If a public base (CDN/CloudFront) is configured, return the plain public URL.
    - Otherwise return a short-lived **presigned** GET URL, so a *private* bucket still serves the
      image without making objects world-readable. (Presigned URLs are generated locally and
      expire after `expires_in` seconds; callers re-derive a fresh one on each read.)
    - Empty key or unconfigured storage => "" (callers fall back to the placeholder initial).
    """
    if not key or not is_configured():
        return ""
    base = settings.AWS_S3_PUBLIC_BASE_URL
    if base:
        return f"{base.rstrip('/')}/{key}"
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET, "Key": key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError):
        return ""


def upload_image(
    data: bytes, content_type: str, *, key_prefix: str = "characters"
) -> tuple[str, str]:
    """Upload image bytes to S3 and return `(public_url, key)`.

    A unique filename is generated per call, so `key_prefix` acts as a folder that can hold many
    images (e.g. `Characters/Project-1/character-2`). The returned `key` is the object's path
    within the bucket — persist it alongside the URL.

    Raises StorageNotConfigured if AWS isn't set up, or StorageError on an upload failure.
    """
    if not is_configured():
        raise StorageNotConfigured(
            "AWS S3 is not configured. Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / "
            "AWS_S3_BUCKET in backend/.env."
        )
    ext = _EXT_BY_TYPE.get((content_type or "").lower(), ".png")
    key = f"{key_prefix.strip('/')}/{uuid.uuid4().hex}{ext}"
    try:
        _client().put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageError(str(exc)) from exc
    return _public_url(key), key


def download(key: str) -> tuple[bytes, str]:
    """Fetch a stored object's bytes and content type by key.

    Exists so the API can *serve* an asset itself rather than handing out a presigned URL.
    A presigned URL expires (an hour by default), which is fine for a browser rendering a
    page and wrong for an agent: a build session outlives the link, and an asset reference
    that dies halfway through a build is worse than no asset at all. Streaming through the
    API gives a stable address that stays valid as long as the object does.

    Raises StorageNotConfigured if AWS isn't set up, or StorageError if the object can't be
    read (missing key, permissions, network).
    """
    if not is_configured():
        raise StorageNotConfigured(
            "Image storage isn't configured — set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, "
            "AWS_REGION and AWS_S3_BUCKET in backend/.env."
        )
    if not key:
        raise StorageError("No object key.")
    try:
        response = _client().get_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
        return response["Body"].read(), response.get("ContentType", "application/octet-stream")
    except (BotoCoreError, ClientError) as exc:
        raise StorageError(str(exc)) from exc
