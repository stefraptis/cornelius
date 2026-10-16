"""Transcode pipeline against a synthetic video: 14 s of reddish "endoscopic"
frames with 4 s of bright grey "room" frames in the middle."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from workers.transcode.pipeline import (
    OutOfBodyConfig,
    blur_filter,
    detect_out_of_body,
    first_in_body_second,
    frame_is_in_body,
    probe,
    sample_frames,
    transcode_video,
)

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("video") / "source.mp4"
    # Three colour segments: body (dark red), room (bright grey), body again.
    # Includes a metadata tag so stripping can be verified.
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x7a1f1f:s=640x360:d=5:r=25",
        "-f",
        "lavfi",
        "-i",
        "color=c=0xd8d8d8:s=640x360:d=4:r=25",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x8a2a22:s=640x360:d=5:r=25",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=14",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-metadata",
        "title=PATIENT NAME SHOULD NOT SURVIVE",
        "-metadata",
        "comment=device-xyz",
        "-shortest",
        str(out),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def test_frame_classifier_on_synthetic_colours() -> None:
    cfg = OutOfBodyConfig()
    red = np.full((36, 64, 3), (122, 31, 31), dtype=np.uint8)
    grey = np.full((36, 64, 3), (216, 216, 216), dtype=np.uint8)
    black = np.zeros((36, 64, 3), dtype=np.uint8)
    blue = np.full((36, 64, 3), (40, 60, 200), dtype=np.uint8)
    assert frame_is_in_body(red, cfg) is True
    assert frame_is_in_body(grey, cfg) is False
    assert frame_is_in_body(black, cfg) is False
    assert frame_is_in_body(blue, cfg) is False


def test_detect_runs_pads_filters_and_merges() -> None:
    cfg = OutOfBodyConfig(min_run_s=2, pad_s=1)
    red = np.full((36, 64, 3), (122, 31, 31), dtype=np.uint8)
    grey = np.full((36, 64, 3), (216, 216, 216), dtype=np.uint8)
    #            0    1     2     3    4    5     6    7     8     9    10
    sequence = [red, grey, grey, red, red, grey, red, grey, grey, grey, red]
    runs = detect_out_of_body(np.stack(sequence), cfg)
    # 1-2 is a run of 2 -> padded to [0,4); 5 alone is dropped; 7-9 -> [6,11)
    assert runs == [(0, 4), (6, 11)]
    assert blur_filter(runs).startswith(
        "boxblur="
    ) and "between(t,0,4)+between(t,6,11)" in blur_filter(runs)
    assert blur_filter([]) == ""
    assert first_in_body_second(100.0, [(0, 12)]) == 12.0
    assert first_in_body_second(100.0, []) == 10.0


def test_full_pipeline(synthetic_video: Path, tmp_path: Path) -> None:
    info = probe(synthetic_video)
    assert 13.5 <= info.duration_s <= 14.5 and info.width == 640 and info.height == 360

    frames = sample_frames(synthetic_video, info.duration_s)
    assert frames.shape[0] >= 13 and frames.shape[3] == 3

    result = transcode_video(synthetic_video, tmp_path / "out")
    assert len(result.sha256) == 64
    # The grey section (5 s to 9 s) is detected and padded by one second.
    assert result.out_of_body == [(4, 10)]

    hls = result.hls_dir
    master = (hls / "master.m3u8").read_text()
    assert "720p.m3u8" in master and "480p.m3u8" in master
    for rendition, height in (("720p", 720), ("480p", 480)):
        playlist = (hls / rendition / "index.m3u8").read_text()
        assert "#EXT-X-ENDLIST" in playlist
        segments = sorted((hls / rendition).glob("seg_*.ts"))
        assert 2 <= len(segments) <= 4, segments  # 14 s in 6 s segments
        out_info = probe(segments[0])
        assert out_info.height == height

    # Metadata stripped from the rendition segments and the proxy.
    for path in (next((hls / "720p").glob("seg_*.ts")), result.proxy):
        tags = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(path)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "PATIENT" not in tags and "device-xyz" not in tags

    assert result.poster.exists() and result.poster.stat().st_size > 1000
    index = json.loads(result.sprite_index.read_text())
    assert index["interval_s"] == 10 and index["count"] == 2 and result.sprite.exists()
    assert probe(result.proxy).height == 360

    # The blurred seconds are visibly different from the sharp ones in the
    # proxy: a flat colour stays flat, so check the blur did not break output
    # by probing the proxy sample at an in-body and an out-of-body second.
    proxy_frames = sample_frames(result.proxy, info.duration_s)
    assert proxy_frames[2].mean() < 100 < proxy_frames[7].mean()
