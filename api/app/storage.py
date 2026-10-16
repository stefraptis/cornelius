"""Object storage, through the S3 API only.

This is the single place that touches object storage (Build Guideline,
Section 3 "Storage portability" and Section 12). Backblaze B2 today; moving to
Cloudflare R2 or MinIO is a configuration change plus a one-time copy, and
nothing outside this module may import boto3.

Rules enforced here:
* Buckets are private. Every read by a browser goes through a short-lived
  presigned URL.
* Video bytes never pass through the API: uploads use presigned multipart
  URLs issued here and completed by the browser directly against storage.
* Keys follow one layout (see `Keys`) so purge and delete can remove a video
  completely by prefix.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import Settings, get_settings

log = logging.getLogger(__name__)


class Keys:
    """Key layout: videos/{video_id}/{original|hls|thumbs|proxy|analysis}/..."""

    @staticmethod
    def video_prefix(video_id: str) -> str:
        return f"videos/{video_id}/"

    @staticmethod
    def original(video_id: str, filename_ext: str) -> str:
        ext = filename_ext.lower().lstrip(".") or "bin"
        return f"videos/{video_id}/original/source.{ext}"

    @staticmethod
    def hls_prefix(video_id: str) -> str:
        return f"videos/{video_id}/hls/"

    @staticmethod
    def thumbs_prefix(video_id: str) -> str:
        return f"videos/{video_id}/thumbs/"

    @staticmethod
    def poster(video_id: str) -> str:
        return f"videos/{video_id}/thumbs/poster.jpg"

    @staticmethod
    def sprite(video_id: str) -> str:
        return f"videos/{video_id}/thumbs/sprite.jpg"

    @staticmethod
    def proxy(video_id: str) -> str:
        return f"videos/{video_id}/proxy/proxy.mp4"

    @staticmethod
    def analysis_prefix(video_id: str, analysis_id: str) -> str:
        return f"videos/{video_id}/analysis/{analysis_id}/"

    @staticmethod
    def report(video_id: str, analysis_id: str) -> str:
        return f"videos/{video_id}/analysis/{analysis_id}/report.html"

    @staticmethod
    def csv_export(video_id: str, analysis_id: str) -> str:
        return f"videos/{video_id}/analysis/{analysis_id}/segments.csv"


@dataclass(frozen=True)
class MultipartUpload:
    key: str
    upload_id: str
    part_size_bytes: int


@dataclass(frozen=True)
class CompletedPart:
    part_number: int
    etag: str


@dataclass(frozen=True)
class ObjectInfo:
    key: str
    size_bytes: int
    etag: str | None = None


class Storage:
    """S3-compatible storage client. Instantiate once per process."""

    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        self.bucket = self.settings.storage_bucket
        self.part_size_bytes = self.settings.storage_multipart_part_mb * 1024 * 1024
        self.presign_ttl = self.settings.storage_presign_ttl_seconds
        self._client = client or boto3.client(
            "s3",
            endpoint_url=self.settings.storage_endpoint_url,
            region_name=self.settings.storage_region,
            aws_access_key_id=self.settings.storage_access_key_id or None,
            aws_secret_access_key=self.settings.storage_secret_access_key or None,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 5, "mode": "standard"},
            ),
        )

    # ---------- presigned reads ----------

    def presign_get(
        self, key: str, ttl_seconds: int | None = None, filename: str | None = None
    ) -> str:
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        return self._client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=ttl_seconds or self.presign_ttl
        )

    # ---------- single-object writes (small files: reports, thumbnails) ----------

    def presign_put(self, key: str, content_type: str, ttl_seconds: int = 900) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=ttl_seconds,
        )

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def upload_file(self, local_path: str, key: str, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.upload_file(local_path, self.bucket, key, ExtraArgs=extra or None)

    def download_file(self, key: str, local_path: str) -> None:
        self._client.download_file(self.bucket, key, local_path)

    # ---------- multipart uploads (large videos, browser -> storage) ----------

    def create_multipart(self, key: str, content_type: str) -> MultipartUpload:
        response = self._client.create_multipart_upload(
            Bucket=self.bucket, Key=key, ContentType=content_type
        )
        return MultipartUpload(
            key=key, upload_id=response["UploadId"], part_size_bytes=self.part_size_bytes
        )

    def presign_part(
        self, key: str, upload_id: str, part_number: int, ttl_seconds: int = 3600
    ) -> str:
        if not 1 <= part_number <= 10000:
            raise ValueError("part_number must be between 1 and 10000")
        return self._client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=ttl_seconds,
        )

    def list_parts(self, key: str, upload_id: str) -> list[CompletedPart]:
        """Parts already stored, so an interrupted upload can resume."""
        parts: list[CompletedPart] = []
        marker = 0
        while True:
            response = self._client.list_parts(
                Bucket=self.bucket, Key=key, UploadId=upload_id, PartNumberMarker=marker
            )
            for part in response.get("Parts", []):
                parts.append(CompletedPart(part_number=part["PartNumber"], etag=part["ETag"]))
            if not response.get("IsTruncated"):
                break
            marker = response["NextPartNumberMarker"]
        return parts

    def complete_multipart(
        self, key: str, upload_id: str, parts: list[CompletedPart]
    ) -> ObjectInfo:
        ordered = sorted(parts, key=lambda p: p.part_number)
        response = self._client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [{"PartNumber": p.part_number, "ETag": p.etag} for p in ordered]
            },
        )
        info = self.head(key)
        return ObjectInfo(key=key, size_bytes=info.size_bytes, etag=response.get("ETag"))

    def abort_multipart(self, key: str, upload_id: str) -> None:
        try:
            self._client.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "NoSuchUpload":
                raise

    # ---------- metadata, listing, deletion ----------

    def head(self, key: str) -> ObjectInfo:
        response = self._client.head_object(Bucket=self.bucket, Key=key)
        return ObjectInfo(
            key=key, size_bytes=int(response["ContentLength"]), etag=response.get("ETag")
        )

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def iter_keys(self, prefix: str) -> Iterator[ObjectInfo]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield ObjectInfo(key=obj["Key"], size_bytes=int(obj["Size"]), etag=obj.get("ETag"))

    def delete_key(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def delete_prefix(self, prefix: str) -> int:
        """Delete every object under a prefix. Returns the number deleted.

        Used by video deletion and the original-purge job. Refuses an empty or
        root prefix so a bug cannot wipe the bucket.
        """
        if not prefix or prefix in ("/", "videos/"):
            raise ValueError("Refusing to delete a root prefix")
        deleted = 0
        batch: list[dict[str, str]] = []
        for obj in self.iter_keys(prefix):
            batch.append({"Key": obj.key})
            if len(batch) == 1000:
                deleted += self._delete_batch(batch)
                batch = []
        if batch:
            deleted += self._delete_batch(batch)
        log.info("storage.delete_prefix", extra={"ctx_prefix": prefix, "ctx_deleted": deleted})
        return deleted

    def _delete_batch(self, objects: list[dict[str, str]]) -> int:
        response = self._client.delete_objects(
            Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True}
        )
        errors = response.get("Errors", [])
        if errors:
            raise RuntimeError(f"Failed to delete {len(errors)} objects: {errors[:3]}")
        return len(objects)

    def prefix_size_bytes(self, prefix: str) -> int:
        return sum(obj.size_bytes for obj in self.iter_keys(prefix))

    # ---------- HLS playlist rewriting (M1 uses this) ----------

    def presign_playlist(
        self, playlist_text: str, hls_prefix: str, ttl_seconds: int | None = None
    ) -> str:
        """Rewrite relative segment and sub-playlist lines into presigned URLs.

        Lines starting with '#' are HLS tags and pass through; a URI attribute
        inside a tag (for example EXT-X-MAP) is also rewritten.
        """
        out: list[str] = []
        for line in playlist_text.splitlines():
            stripped = line.strip()
            if not stripped:
                out.append(line)
                continue
            if stripped.startswith("#"):
                if 'URI="' in stripped:
                    start = stripped.index('URI="') + 5
                    end = stripped.index('"', start)
                    uri = stripped[start:end]
                    if not uri.startswith(("http://", "https://")):
                        uri = self.presign_get(hls_prefix + uri, ttl_seconds)
                    stripped = stripped[:start] + uri + stripped[end:]
                out.append(stripped)
                continue
            if stripped.startswith(("http://", "https://")):
                out.append(stripped)
                continue
            out.append(self.presign_get(hls_prefix + stripped, ttl_seconds))
        return "\n".join(out) + "\n"


@lru_cache
def get_storage() -> Storage:
    return Storage()
