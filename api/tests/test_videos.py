"""Upload sessions, library, playback endpoints, deletion. Storage is moto."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import boto3
import psycopg
import pytest
import requests
from fastapi.testclient import TestClient
from moto import mock_aws

from app import db
from app.config import Settings
from app.main import create_app
from app.storage import Keys, Storage, get_storage
from tests.conftest import make_token
from tests.dbtest import as_service, create_auth_user, recreate_database, server_reachable

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def env(settings: Settings) -> Iterator[tuple[TestClient, Storage]]:
    if not server_reachable(settings.database_url):
        pytest.skip("PostgreSQL not reachable at DATABASE_URL; run `make db-local`")
    recreate_database(settings.database_url)
    db.close_pool()
    with mock_aws():
        client = boto3.client("s3", region_name=settings.storage_region)
        client.create_bucket(
            Bucket=settings.storage_bucket,
            CreateBucketConfiguration={"LocationConstraint": settings.storage_region},
        )
        storage = Storage(settings=settings, client=client)
        app = create_app()
        app.dependency_overrides[get_storage] = lambda: storage
        with TestClient(app) as test_client:
            yield test_client, storage
    db.close_pool()


@pytest.fixture(scope="module")
def users(settings: Settings, env: tuple[TestClient, Storage]) -> dict[str, uuid.UUID]:
    with psycopg.connect(settings.database_url) as conn:
        alice = create_auth_user(conn, "alice-v@example.org", "Alice")
        bob = create_auth_user(conn, "bob-v@example.org", "Bob")
    return {"alice": alice, "bob": bob}


def auth(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id)}"}


NEW = {
    "title": "LC case 1",
    "procedure_code": "lc",
    "operation_date": "2026-10-01",
    "filename": "Video_05.MP4",
    "size_bytes": 6 * 1024 * 1024,
    "consent_confirmed": True,
}


def test_create_upload_validations(
    env: tuple[TestClient, Storage], users: dict[str, uuid.UUID]
) -> None:
    client, _ = env
    h = auth(users["alice"])
    assert (
        client.post("/videos", json={**NEW, "consent_confirmed": False}, headers=h).status_code
        == 422
    )
    assert (
        client.post("/videos", json={**NEW, "filename": "notes.txt"}, headers=h).status_code == 422
    )
    assert (
        client.post("/videos", json={**NEW, "procedure_code": "nope"}, headers=h).status_code == 422
    )
    assert (
        client.post("/videos", json={**NEW, "size_bytes": 21 * 10**9}, headers=h).status_code == 413
    )


def test_full_upload_flow(
    env: tuple[TestClient, Storage], users: dict[str, uuid.UUID], settings: Settings
) -> None:
    client, storage = env
    h = auth(users["alice"])
    r = client.post("/videos", json=NEW, headers=h)
    assert r.status_code == 201, r.text
    session = r.json()
    vid = session["video_id"]
    assert session["key"] == Keys.original(vid, "mp4")
    assert session["part_size_bytes"] == 64 * 1024 * 1024 and session["part_count"] == 1

    # The browser uploads parts through presigned URLs.
    completed = []
    for n, data in ((1, b"a" * (5 * 1024 * 1024)), (2, b"b" * 1024)):
        url = client.get(f"/videos/{vid}/upload/part/{n}", headers=h).json()["url"]
        put = requests.put(url, data=data, timeout=30)
        assert put.status_code == 200
        completed.append({"part_number": n, "etag": put.headers["ETag"]})

    # Resume listing sees both parts; another user sees nothing.
    assert [
        p["part_number"] for p in client.get(f"/videos/{vid}/upload/parts", headers=h).json()
    ] == [1, 2]
    assert client.get(f"/videos/{vid}/upload/parts", headers=auth(users["bob"])).status_code == 404

    r = client.post(f"/videos/{vid}/upload/complete", json={"parts": completed}, headers=h)
    assert r.status_code == 200, r.text
    video = r.json()
    assert video["status"] == "processing"
    assert video["size_bytes"] == 5 * 1024 * 1024 + 1024
    assert video["procedure_name"] == "Laparoscopic cholecystectomy"
    assert video["analysis_requested"] is True
    assert storage.exists(Keys.original(vid, "mp4"))

    with as_service(settings.database_url) as conn:
        job = conn.execute(
            "select type::text as type, payload from public.jobs where video_id = %s", (vid,)
        ).fetchone()
    assert job["type"] == "transcode" and job["payload"]["original_key"] == Keys.original(
        vid, "mp4"
    )

    # Completing twice is refused; parts can no longer be signed.
    assert (
        client.post(
            f"/videos/{vid}/upload/complete", json={"parts": completed}, headers=h
        ).status_code
        == 409
    )
    assert client.get(f"/videos/{vid}/upload/part/1", headers=h).status_code == 409

    usage = client.get("/videos/storage", headers=h).json()
    assert (
        usage["videos"] == 1
        and usage["used_bytes"] == video["size_bytes"]
        and usage["quota_bytes"] == 20_000_000_000
    )


def test_abort_upload_removes_row(
    env: tuple[TestClient, Storage], users: dict[str, uuid.UUID]
) -> None:
    client, storage = env
    h = auth(users["alice"])
    vid = client.post("/videos", json={**NEW, "title": "Aborted"}, headers=h).json()["video_id"]
    assert client.delete(f"/videos/{vid}/upload", headers=h).status_code == 204
    assert client.get(f"/videos/{vid}", headers=h).status_code == 404
    assert not storage.exists(Keys.original(vid, "mp4"))


def test_library_listing_filters_and_isolation(
    env: tuple[TestClient, Storage], users: dict[str, uuid.UUID]
) -> None:
    client, _ = env
    a, b = auth(users["alice"]), auth(users["bob"])
    client.post(
        "/videos",
        json={**NEW, "title": "Bob private", "procedure_code": "robotic_chole"},
        headers=b,
    )

    mine = client.get("/videos", headers=a).json()
    assert [v["title"] for v in mine] == ["LC case 1"]
    assert mine[0]["is_owner"] is True and mine[0]["permission"] == "owner"
    assert client.get("/videos?scope=all", headers=a).json()[0]["title"] == "LC case 1"
    assert [v["title"] for v in client.get("/videos", headers=b).json()] == ["Bob private"]

    assert client.get("/videos?q=case", headers=a).json()[0]["title"] == "LC case 1"
    assert client.get("/videos?q=zzz", headers=a).json() == []
    assert client.get("/videos?procedure=robotic_chole", headers=a).json() == []
    assert client.get("/videos?status=processing", headers=a).json()[0]["title"] == "LC case 1"
    assert client.get("/videos?status=uploading", headers=a).json() == []
    assert client.get("/videos?date_from=2026-10-02", headers=a).json() == []
    assert client.get("/videos?status=drop%20table", headers=a).status_code == 422

    vid = mine[0]["id"]
    assert client.get(f"/videos/{vid}", headers=b).status_code == 404
    assert client.patch(f"/videos/{vid}", json={"title": "Hijack"}, headers=b).status_code == 404
    r = client.patch(f"/videos/{vid}", json={"title": "LC case 1 (renamed)"}, headers=a)
    assert r.status_code == 200 and r.json()["title"] == "LC case 1 (renamed)"


def test_playback_before_transcode_and_after(
    env: tuple[TestClient, Storage], users: dict[str, uuid.UUID], settings: Settings
) -> None:
    client, storage = env
    a = auth(users["alice"])
    vid = client.get("/videos", headers=a).json()[0]["id"]
    assert client.get(f"/videos/{vid}/stream.m3u8", headers=a).status_code == 409

    # Simulate the worker's output.
    hls = Keys.hls_prefix(vid)
    storage.put_bytes(
        hls + "master.m3u8",
        b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720\n720p.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=854x480\n480p.m3u8\n",
        "application/vnd.apple.mpegurl",
    )
    storage.put_bytes(
        hls + "720p/index.m3u8",
        b"#EXTM3U\n#EXTINF:6.0,\nseg_000.ts\n#EXTINF:6.0,\nseg_001.ts\n#EXT-X-ENDLIST\n",
        "application/vnd.apple.mpegurl",
    )
    storage.put_bytes(Keys.poster(vid), b"jpg", "image/jpeg")
    with as_service(settings.database_url) as conn:
        conn.execute(
            "update public.videos set status='ready', hls_prefix=%s, thumbnail_key=%s, duration_s=1200 where id=%s",
            (hls, Keys.poster(vid), vid),
        )
        conn.commit()

    master = client.get(f"/videos/{vid}/stream.m3u8", headers=a)
    assert master.status_code == 200 and master.headers["content-type"].startswith(
        "application/vnd.apple.mpegurl"
    )
    assert (
        f"/videos/{vid}/stream/720p.m3u8" in master.text
        and f"/videos/{vid}/stream/480p.m3u8" in master.text
    )

    rendition = client.get(f"/videos/{vid}/stream/720p.m3u8", headers=a)
    assert rendition.status_code == 200
    lines = [ln for ln in rendition.text.splitlines() if ln and not ln.startswith("#")]
    assert len(lines) == 2 and all(
        ln.startswith("https://") and "X-Amz-Signature" in ln for ln in lines
    )
    assert client.get(f"/videos/{vid}/stream/480p.m3u8", headers=a).status_code == 404
    assert client.get(f"/videos/{vid}/stream.m3u8", headers=auth(users["bob"])).status_code == 404

    with as_service(settings.database_url) as conn:
        est = conn.execute(
            "select bytes_estimated from public.streaming_usage where video_id = %s", (vid,)
        ).fetchone()
        views = conn.execute(
            "select count(*) as n from public.audit_log where object_id = %s and action = 'video.stream'",
            (vid,),
        ).fetchone()["n"]
    assert est["bytes_estimated"] == int(1200 * 2_000_000 / 8) and views == 1

    poster = client.get(f"/videos/{vid}/assets/poster", headers=a).json()["url"]
    assert "X-Amz-Signature" in poster
    assert (
        client.get(f"/videos/{vid}/assets/original", headers=auth(users["bob"])).status_code == 404
    )
    assert client.get("/videos", headers=a).json()[0]["poster_url"].startswith("https://")


def test_delete_video_soft_deletes_and_queues_purge(
    env: tuple[TestClient, Storage], users: dict[str, uuid.UUID], settings: Settings
) -> None:
    client, _ = env
    a = auth(users["alice"])
    vid = client.get("/videos", headers=a).json()[0]["id"]
    assert client.delete(f"/videos/{vid}", headers=auth(users["bob"])).status_code == 404
    assert client.delete(f"/videos/{vid}", headers=a).status_code == 204
    assert client.get(f"/videos/{vid}", headers=a).status_code == 404
    assert client.get("/videos", headers=a).json() == []
    with as_service(settings.database_url) as conn:
        job = conn.execute(
            "select payload from public.jobs where video_id = %s and type = 'purge'", (vid,)
        ).fetchone()
    assert job["payload"] == {"prefixes": [f"videos/{vid}/"], "hard_delete": True}
