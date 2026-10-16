"""Storage module tests against an in-memory S3 (moto).

The same tests can run against a real B2 test bucket by setting
STORAGE_* variables and STORAGE_LIVE_TEST=1 (see test_storage_live.py).
"""

from __future__ import annotations

import pytest
import requests

from app.storage import CompletedPart, Keys, Storage

VIDEO_ID = "0f6a0b7e-6b7d-4a4f-9d2a-6b0f8a7e1c11"


def test_key_layout_is_under_one_video_prefix() -> None:
    prefix = Keys.video_prefix(VIDEO_ID)
    for key in (
        Keys.original(VIDEO_ID, ".MP4"),
        Keys.poster(VIDEO_ID),
        Keys.sprite(VIDEO_ID),
        Keys.proxy(VIDEO_ID),
        Keys.report(VIDEO_ID, "an1"),
        Keys.csv_export(VIDEO_ID, "an1"),
        Keys.hls_prefix(VIDEO_ID) + "720p/seg_000.ts",
    ):
        assert key.startswith(prefix)
    assert Keys.original(VIDEO_ID, ".MP4").endswith("/original/source.mp4")


def test_put_get_head_exists_delete(storage: Storage) -> None:
    key = Keys.poster(VIDEO_ID)
    assert storage.exists(key) is False
    storage.put_bytes(key, b"jpegdata", "image/jpeg")
    assert storage.exists(key) is True
    assert storage.head(key).size_bytes == 8
    assert storage.get_bytes(key) == b"jpegdata"
    storage.delete_key(key)
    assert storage.exists(key) is False


def test_presigned_get_url_is_time_limited_and_signed(storage: Storage) -> None:
    key = Keys.report(VIDEO_ID, "an1")
    storage.put_bytes(key, b"<html></html>", "text/html")
    url = storage.presign_get(key, ttl_seconds=120)
    assert "X-Amz-Expires=120" in url
    assert "X-Amz-Signature=" in url
    assert key in url
    body = requests.get(url, timeout=10).content
    assert body == b"<html></html>"


def test_presigned_download_sets_filename(storage: Storage) -> None:
    key = Keys.csv_export(VIDEO_ID, "an1")
    url = storage.presign_get(key, filename="segments.csv")
    assert "response-content-disposition=" in url


def test_multipart_upload_round_trip_and_resume_listing(storage: Storage) -> None:
    key = Keys.original(VIDEO_ID, "mp4")
    upload = storage.create_multipart(key, "video/mp4")
    assert upload.part_size_bytes == 64 * 1024 * 1024

    # The browser uploads parts directly with presigned URLs. Here we upload
    # two parts through signed URLs (part 1 must be >= 5 MB in real S3).
    part_bytes = b"a" * (5 * 1024 * 1024)
    completed: list[CompletedPart] = []
    for n, data in ((1, part_bytes), (2, b"tail")):
        url = storage.presign_part(key, upload.upload_id, n)
        assert f"partNumber={n}" in url and "uploadId=" in url
        response = requests.put(url, data=data, timeout=30)
        assert response.status_code == 200
        completed.append(CompletedPart(part_number=n, etag=response.headers["ETag"]))

    # Resume support: parts already stored are listable.
    listed = storage.list_parts(key, upload.upload_id)
    assert sorted(p.part_number for p in listed) == [1, 2]

    info = storage.complete_multipart(key, upload.upload_id, completed)
    assert info.size_bytes == len(part_bytes) + 4
    assert storage.exists(key)


def test_abort_multipart_is_idempotent(storage: Storage) -> None:
    key = Keys.original(VIDEO_ID, "mov")
    upload = storage.create_multipart(key, "video/quicktime")
    storage.abort_multipart(key, upload.upload_id)
    storage.abort_multipart(key, upload.upload_id)  # NoSuchUpload is swallowed
    assert storage.exists(key) is False


def test_presign_part_rejects_out_of_range(storage: Storage) -> None:
    with pytest.raises(ValueError):
        storage.presign_part("k", "u", 0)
    with pytest.raises(ValueError):
        storage.presign_part("k", "u", 10001)


def test_delete_prefix_removes_everything_for_one_video_only(storage: Storage) -> None:
    other = "other-video"
    for key in (
        Keys.original(VIDEO_ID, "mp4"),
        Keys.poster(VIDEO_ID),
        Keys.hls_prefix(VIDEO_ID) + "720p/index.m3u8",
        Keys.hls_prefix(VIDEO_ID) + "720p/seg_000.ts",
        Keys.report(VIDEO_ID, "an1"),
        Keys.poster(other),
    ):
        storage.put_bytes(key, b"x", "application/octet-stream")

    assert storage.prefix_size_bytes(Keys.video_prefix(VIDEO_ID)) == 5
    deleted = storage.delete_prefix(Keys.video_prefix(VIDEO_ID))
    assert deleted == 5
    assert list(storage.iter_keys(Keys.video_prefix(VIDEO_ID))) == []
    assert storage.exists(Keys.poster(other))  # untouched


def test_delete_prefix_refuses_root(storage: Storage) -> None:
    for bad in ("", "/", "videos/"):
        with pytest.raises(ValueError):
            storage.delete_prefix(bad)


def test_presign_playlist_rewrites_segments_and_map_uri(storage: Storage) -> None:
    hls_prefix = Keys.hls_prefix(VIDEO_ID) + "720p/"
    playlist = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:7\n"
        '#EXT-X-MAP:URI="init.mp4"\n'
        "#EXTINF:6.000,\n"
        "seg_000.m4s\n"
        "#EXTINF:6.000,\n"
        "seg_001.m4s\n"
        "#EXT-X-ENDLIST\n"
    )
    out = storage.presign_playlist(playlist, hls_prefix, ttl_seconds=7200)
    lines = out.strip().splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[2].startswith('#EXT-X-MAP:URI="https://') and "init.mp4" in lines[2]
    assert lines[4].startswith("https://") and "seg_000.m4s" in lines[4]
    assert "X-Amz-Expires=7200" in lines[4]
    assert lines[6].startswith("https://") and "seg_001.m4s" in lines[6]
    assert lines[-1] == "#EXT-X-ENDLIST"
