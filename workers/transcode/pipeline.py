"""Transcode and anonymize one video with ffmpeg (Build Guideline, Section 5.2).

Steps, each a small function so they can be tested on their own:

1. probe: duration, resolution, frame rate (ffprobe).
2. sha256 of the original, for duplicate detection.
3. out-of-body detection: sample one frame per second at low resolution and
   flag seconds whose colour statistics do not look endoscopic. Endoscopic
   frames are dominated by red and orange hues with a dark vignette; room
   footage is bright, grey or blue, with little red dominance. Thresholds are
   configurable and conservative; a trained classifier replaces this later.
4. renditions: HLS 720p (about 2 Mbps) and 480p (about 1 Mbps), H.264,
   6-second segments, with every container metadata tag stripped and the
   flagged seconds blurred. One ffmpeg run produces both renditions.
5. poster (first in-body second), sprite sheet (one thumbnail every 10 s,
   10 columns) with its index JSON, and a 360p proxy MP4 for annotation.

Nothing here touches the database or object storage; `main.py` does the
download, upload and bookkeeping around `transcode_video()`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger("worker.transcode")

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")

SEGMENT_SECONDS = 6
SPRITE_INTERVAL_S = 10
SPRITE_COLUMNS = 10
SPRITE_TILE = (160, 90)


@dataclass
class Probe:
    duration_s: float
    width: int
    height: int
    fps: float


@dataclass
class OutOfBodyConfig:
    """Thresholds for the colour heuristic; tuned to be conservative."""

    sample_width: int = 64
    # A frame is "in body" when red clearly dominates the other channels.
    min_red_dominance: float = 0.12  # mean(R) - mean(max(G, B)) over [0, 1]
    # Very bright, low-saturation frames (room, drapes, screens) are out of body.
    max_brightness: float = 0.70
    min_saturation: float = 0.12
    # Ignore blips: an out-of-body run shorter than this is kept unblurred.
    min_run_s: int = 2
    # Extend each run by this margin on both sides, to catch transition frames.
    pad_s: int = 1


@dataclass
class TranscodeResult:
    probe: Probe
    sha256: str
    out_of_body: list[tuple[int, int]]  # [start_s, end_s) runs that were blurred
    hls_dir: Path
    poster: Path
    sprite: Path
    sprite_index: Path
    proxy: Path
    renditions: list[str] = field(default_factory=lambda: ["720p", "480p"])


# ---------- 1. probe ----------


def probe(path: Path) -> Probe:
    out = subprocess.run(  # noqa: S603
        [
            FFPROBE,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    data = json.loads(out)
    stream = data["streams"][0]
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "25/1"
    num, _, den = rate.partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 25.0
    return Probe(
        duration_s=float(data["format"]["duration"]),
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=fps or 25.0,
    )


# ---------- 2. hash ----------


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------- 3. out-of-body detection ----------


def sample_frames(path: Path, duration_s: float, width: int = 64) -> np.ndarray:
    """One frame per second as an array of shape (seconds, h, w, 3), uint8."""
    height = max(2, int(round(width * 9 / 16)))
    seconds = max(1, int(math.ceil(duration_s)))
    raw = subprocess.run(  # noqa: S603
        [
            FFMPEG,
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"fps=1,scale={width}:{height}",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    frame_bytes = width * height * 3
    count = min(seconds, len(raw) // frame_bytes)
    frames = np.frombuffer(raw[: count * frame_bytes], dtype=np.uint8).reshape(
        count, height, width, 3
    )
    return frames


def frame_is_in_body(frame: np.ndarray, config: OutOfBodyConfig) -> bool:
    rgb = frame.astype(np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    brightness = float(rgb.mean())
    red_dominance = float((r - np.maximum(g, b)).mean())
    mx = rgb.max(axis=-1)
    mn = rgb.min(axis=-1)
    saturation = float(np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0).mean())
    if red_dominance >= config.min_red_dominance:
        return True
    if brightness > config.max_brightness and saturation < config.min_saturation:
        return False
    # Dim and grey (dark room, black frames) or coloured but not red: treat as
    # out of body only when there is clearly no red tint at all.
    return red_dominance > 0.02


def detect_out_of_body(frames: np.ndarray, config: OutOfBodyConfig) -> list[tuple[int, int]]:
    """Return [start_s, end_s) runs of out-of-body seconds, padded and filtered."""
    flags = [not frame_is_in_body(frame, config) for frame in frames]
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for second, out in enumerate(flags + [False]):
        if out and start is None:
            start = second
        elif not out and start is not None:
            if second - start >= config.min_run_s:
                runs.append((max(0, start - config.pad_s), min(len(flags), second + config.pad_s)))
            start = None
    # Merge runs that now overlap after padding.
    merged: list[tuple[int, int]] = []
    for s, e in runs:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def blur_filter(runs: list[tuple[int, int]]) -> str:
    """ffmpeg filter that blurs the given second ranges (empty string if none)."""
    if not runs:
        return ""
    conditions = "+".join(f"between(t,{s},{e})" for s, e in runs)
    return f"boxblur=luma_radius=20:luma_power=3:chroma_radius=10:enable='{conditions}'"


# ---------- 4. renditions ----------


def transcode_hls(src: Path, out_dir: Path, runs: list[tuple[int, int]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for rendition in ("720p", "480p"):
        (out_dir / rendition).mkdir(exist_ok=True)
    blur = blur_filter(runs)
    pre = f"{blur}," if blur else ""
    filter_complex = (
        f"[0:v]{pre}split=2[v720][v480];[v720]scale=-2:720[o720];[v480]scale=-2:480[o480]"
    )
    cmd = [
        FFMPEG,
        "-v",
        "error",
        "-y",
        "-i",
        str(src),
        "-filter_complex",
        filter_complex,
        # Strip all metadata and chapters from the output containers.
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-sn",
        "-dn",
    ]
    for label, out_name, bitrate, maxrate, bufsize in (
        ("o720", "720p", "2000k", "2400k", "4000k"),
        ("o480", "480p", "1000k", "1200k", "2000k"),
    ):
        cmd += [
            "-map",
            f"[{label}]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-profile:v",
            "main",
            "-b:v",
            bitrate,
            "-maxrate",
            maxrate,
            "-bufsize",
            bufsize,
            "-g",
            "48",
            "-keyint_min",
            "48",
            "-sc_threshold",
            "0",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-ac",
            "2",
            "-hls_time",
            str(SEGMENT_SECONDS),
            "-hls_playlist_type",
            "vod",
            "-hls_segment_type",
            "mpegts",
            "-hls_flags",
            "independent_segments",
            "-hls_segment_filename",
            str(out_dir / out_name / "seg_%04d.ts"),
            str(out_dir / out_name / "index.m3u8"),
        ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)  # noqa: S603
    master = (
        "#EXTM3U\n#EXT-X-VERSION:3\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=2300000,RESOLUTION=1280x720,CODECS="avc1.4d401f,mp4a.40.2"\n'
        "720p.m3u8\n"
        '#EXT-X-STREAM-INF:BANDWIDTH=1150000,RESOLUTION=854x480,CODECS="avc1.4d401e,mp4a.40.2"\n'
        "480p.m3u8\n"
    )
    (out_dir / "master.m3u8").write_text(master, encoding="utf-8")


# ---------- 5. stills and proxy ----------


def first_in_body_second(duration_s: float, runs: list[tuple[int, int]]) -> float:
    candidate = min(duration_s * 0.1, 30.0)
    for s, e in runs:
        if s <= candidate < e:
            candidate = float(e)
    return min(candidate, max(0.0, duration_s - 1))


def make_poster(src: Path, out: Path, at_s: float, runs: list[tuple[int, int]]) -> None:
    blur = blur_filter(runs)
    vf = f"{blur}," if blur else ""
    subprocess.run(  # noqa: S603
        [
            FFMPEG,
            "-v",
            "error",
            "-y",
            "-ss",
            f"{at_s:.3f}",
            "-i",
            str(src),
            "-vf",
            f"{vf}scale=-2:720",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(out),
        ],
        check=True,
        capture_output=True,
    )


def make_sprite(
    src: Path, out_image: Path, out_index: Path, duration_s: float, runs: list[tuple[int, int]]
) -> None:
    """One tile every SPRITE_INTERVAL_S seconds, SPRITE_COLUMNS per row."""
    w, h = SPRITE_TILE
    count = max(1, int(math.floor(duration_s / SPRITE_INTERVAL_S)) + 1)
    rows = int(math.ceil(count / SPRITE_COLUMNS))
    blur = blur_filter(runs)
    vf = f"{blur}," if blur else ""
    raw = subprocess.run(  # noqa: S603
        [
            FFMPEG,
            "-v",
            "error",
            "-i",
            str(src),
            "-vf",
            f"{vf}fps=1/{SPRITE_INTERVAL_S}:round=up,scale={w}:{h}",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    frame_bytes = w * h * 3
    tiles = min(count, len(raw) // frame_bytes)
    sheet = Image.new("RGB", (SPRITE_COLUMNS * w, rows * h), (17, 19, 17))
    for i in range(tiles):
        tile = Image.frombytes("RGB", (w, h), raw[i * frame_bytes : (i + 1) * frame_bytes])
        sheet.paste(tile, ((i % SPRITE_COLUMNS) * w, (i // SPRITE_COLUMNS) * h))
    sheet.save(out_image, "JPEG", quality=70, optimize=True)
    out_index.write_text(
        json.dumps(
            {
                "interval_s": SPRITE_INTERVAL_S,
                "tile_width": w,
                "tile_height": h,
                "columns": SPRITE_COLUMNS,
                "count": tiles,
            }
        ),
        encoding="utf-8",
    )


def make_proxy(src: Path, out: Path, runs: list[tuple[int, int]]) -> None:
    blur = blur_filter(runs)
    vf = f"{blur}," if blur else ""
    subprocess.run(  # noqa: S603
        [
            FFMPEG,
            "-v",
            "error",
            "-y",
            "-i",
            str(src),
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-sn",
            "-dn",
            "-vf",
            f"{vf}scale=-2:360",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "28",
            "-g",
            "25",
            "-movflags",
            "+faststart",
            "-an",
            str(out),
        ],
        check=True,
        capture_output=True,
    )


# ---------- orchestration ----------


def transcode_video(
    src: Path, work_dir: Path, config: OutOfBodyConfig | None = None
) -> TranscodeResult:
    config = config or OutOfBodyConfig()
    work_dir.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    digest = sha256_of(src)
    frames = sample_frames(src, info.duration_s, config.sample_width)
    runs = detect_out_of_body(frames, config)
    log.info("transcode.out_of_body runs=%s duration=%.1f", runs, info.duration_s)

    hls_dir = work_dir / "hls"
    transcode_hls(src, hls_dir, runs)
    thumbs = work_dir / "thumbs"
    thumbs.mkdir(exist_ok=True)
    poster = thumbs / "poster.jpg"
    make_poster(src, poster, first_in_body_second(info.duration_s, runs), runs)
    sprite = thumbs / "sprite.jpg"
    sprite_index = thumbs / "sprite.json"
    make_sprite(src, sprite, sprite_index, info.duration_s, runs)
    proxy_dir = work_dir / "proxy"
    proxy_dir.mkdir(exist_ok=True)
    proxy = proxy_dir / "proxy.mp4"
    make_proxy(src, proxy, runs)

    return TranscodeResult(
        probe=info,
        sha256=digest,
        out_of_body=runs,
        hls_dir=hls_dir,
        poster=poster,
        sprite=sprite,
        sprite_index=sprite_index,
        proxy=proxy,
    )
