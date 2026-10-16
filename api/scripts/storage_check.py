"""Configure and verify the object storage bucket (Backblaze B2 or any S3 API).

    python scripts/storage_check.py            # configure CORS, then run the live checks
    python scripts/storage_check.py --no-cors  # only run the checks

Checks, in order: credentials and bucket access, CORS rules for browser
uploads, presigned read, multipart upload with part listing (resume),
completion and size, prefix deletion, and that the bucket is private.
Everything it creates lives under the prefix `videos/_storage_check/` and is
deleted at the end.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import requests
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402
from app.storage import CompletedPart, Storage  # noqa: E402

CORS_RULES = {
    "CORSRules": [
        {
            "AllowedOrigins": ["http://localhost:3100", "http://127.0.0.1:3100"],
            "AllowedMethods": ["GET", "PUT", "HEAD"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag", "Content-Length", "Content-Type", "x-amz-request-id"],
            "MaxAgeSeconds": 3600,
        }
    ]
}


def step(name: str) -> None:
    print(f"\n== {name}")


def main(argv: list[str]) -> int:
    settings = get_settings()
    extra_origins = [
        o for o in settings.cors_origins if o not in CORS_RULES["CORSRules"][0]["AllowedOrigins"]
    ]
    CORS_RULES["CORSRules"][0]["AllowedOrigins"].extend(extra_origins)

    storage = Storage(settings)
    client = storage._client  # noqa: SLF001
    bucket = settings.storage_bucket
    print(f"Endpoint {settings.storage_endpoint_url}")
    print(f"Bucket {bucket}, region {settings.storage_region}")

    step("1. Credentials and bucket access")
    try:
        client.head_bucket(Bucket=bucket)
        print("ok: bucket reachable with this key")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        print(f"FAILED: {code}: {exc}")
        if code in ("403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
            print("Check STORAGE_ACCESS_KEY_ID and STORAGE_SECRET_ACCESS_KEY,")
            print("and that the key is allowed to access this bucket.")
        if code in ("404", "NoSuchBucket"):
            print("Check STORAGE_BUCKET; the bucket name must match exactly.")
        return 1

    if "--no-cors" not in argv:
        step("2. CORS rules for browser uploads")
        try:
            client.put_bucket_cors(Bucket=bucket, CORSConfiguration=CORS_RULES)
            print("ok: CORS rules set for", ", ".join(CORS_RULES["CORSRules"][0]["AllowedOrigins"]))
        except ClientError as exc:
            print(f"WARNING: could not set CORS through the S3 API: {exc}")
            print(
                "Set them with the B2 CLI instead: b2 bucket update --cors-rules '<json>' "
                f"{bucket} allPrivate (see docs/setup.md)."
            )
        try:
            current = client.get_bucket_cors(Bucket=bucket)
            print("current rules:", current.get("CORSRules"))
        except ClientError as exc:
            print(f"note: cannot read CORS rules: {exc.response.get('Error', {}).get('Code')}")

    prefix = f"videos/_storage_check/{uuid.uuid4().hex[:8]}/"
    try:
        step("3. Small object, presigned read")
        key = prefix + "poster.jpg"
        storage.put_bytes(key, b"jpeg-bytes", "image/jpeg")
        url = storage.presign_get(key, ttl_seconds=120)
        body = requests.get(url, timeout=30)
        assert body.status_code == 200 and body.content == b"jpeg-bytes", body.status_code
        print("ok: presigned GET works, expires in 120 s")

        step("4. Private bucket")
        anon = requests.get(f"{settings.storage_endpoint_url}/{bucket}/{key}", timeout=30)
        if anon.status_code in (401, 403):
            print(f"ok: anonymous read refused ({anon.status_code})")
        else:
            print(f"FAILED: anonymous read returned {anon.status_code}; the bucket must be private")
            return 1

        step("5. Multipart upload with resume listing (2 parts, 5 MB + small)")
        mkey = prefix + "original/source.mp4"
        upload = storage.create_multipart(mkey, "video/mp4")
        part1 = b"a" * (5 * 1024 * 1024)
        parts: list[CompletedPart] = []
        for n, data in ((1, part1), (2, b"tail-bytes")):
            purl = storage.presign_part(mkey, upload.upload_id, n)
            r = requests.put(purl, data=data, timeout=120)
            assert r.status_code == 200, f"part {n}: {r.status_code} {r.text[:200]}"
            parts.append(CompletedPart(part_number=n, etag=r.headers["ETag"]))
        listed = storage.list_parts(mkey, upload.upload_id)
        assert sorted(p.part_number for p in listed) == [1, 2], listed
        print("ok: parts uploaded through presigned URLs and listed for resume")
        info = storage.complete_multipart(mkey, upload.upload_id, parts)
        assert info.size_bytes == len(part1) + 10, info
        print(f"ok: multipart completed, {info.size_bytes} bytes")

        step("6. Delete by prefix")
        deleted = storage.delete_prefix(prefix)
        assert deleted == 2, deleted
        assert list(storage.iter_keys(prefix)) == []
        print("ok: 2 objects deleted, prefix empty")
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}")
        try:
            storage.delete_prefix(prefix)
        except Exception as cleanup_exc:  # noqa: BLE001
            print(f"cleanup failed, remove {prefix} by hand: {cleanup_exc}")
        return 1

    print("\nAll storage checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
