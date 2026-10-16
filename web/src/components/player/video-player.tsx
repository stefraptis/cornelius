"use client";

/**
 * Player with hls.js and a custom control bar (Build Guideline, Section 7).
 *
 * The playlist comes from the API, which checks access and presigns every
 * segment, so hls.js needs the user's token on playlist requests only.
 * Below the scrubber there is room for the phase band, tool lane and event
 * markers; they are rendered by the parent through `timelineExtras` once an
 * analysis exists (M2).
 */
import Hls, { type Level } from "hls.js";
import { Maximize, Minimize, Pause, Play, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useImperativeHandle, useRef, useState, forwardRef } from "react";

import { Button } from "@/components/ui/button";
import { t } from "@/lib/i18n";
import { useLocalPref } from "@/lib/local-pref";
import { cn, formatTimestamp } from "@/lib/utils";

export type PlayerHandle = {
  seek: (seconds: number) => void;
  play: () => void;
  pause: () => void;
  currentTime: () => number;
};

export type SpriteIndex = { interval_s: number; tile_width: number; tile_height: number; columns: number; count: number };

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];
const FRAME_S = 1 / 25;

export const VideoPlayer = forwardRef<
  PlayerHandle,
  {
    videoId: string;
    src: string;
    getToken: () => Promise<string | null>;
    duration?: number | null;
    sprite?: { url: string; index: SpriteIndex } | null;
    phaseBoundaries?: number[];
    timelineExtras?: React.ReactNode;
    onTime?: (seconds: number) => void;
  }
>(function VideoPlayer({ videoId, src, getToken, duration, sprite, phaseBoundaries = [], timelineExtras, onTime }, ref) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [length, setLength] = useState(duration ?? 0);
  const [buffered, setBuffered] = useState(0);
  const [muted, setMuted] = useState(false);
  const [speed, setSpeed] = useLocalPref("cornelius.player.speed", "1");
  const [levels, setLevels] = useState<Level[]>([]);
  const [level, setLevel] = useState(-1);
  const [fullscreen, setFullscreen] = useState(false);
  const [hover, setHover] = useState<{ x: number; t: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const positionKey = `cornelius.position.${videoId}`;

  const seek = useCallback((seconds: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(seconds, v.duration || seconds));
  }, []);

  useImperativeHandle(ref, () => ({
    seek,
    play: () => void videoRef.current?.play(),
    pause: () => videoRef.current?.pause(),
    currentTime: () => videoRef.current?.currentTime ?? 0,
  }));

  // hls.js setup with the bearer token on playlist requests.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let cancelled = false;
    let hls: Hls | null = null;
    (async () => {
      const token = await getToken();
      if (cancelled || !token) return;
      if (Hls.isSupported()) {
        hls = new Hls({
          xhrSetup: (xhr, url) => {
            if (url.startsWith(src.split("/videos/")[0])) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
          },
          maxBufferLength: 30,
        });
        hlsRef.current = hls;
        hls.on(Hls.Events.MANIFEST_PARSED, (_e, data) => setLevels(data.levels));
        hls.on(Hls.Events.LEVEL_SWITCHED, (_e, data) => setLevel(hls?.autoLevelEnabled ? -1 : data.level));
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (data.fatal) setError(data.details);
        });
        hls.loadSource(src);
        hls.attachMedia(video);
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        // Safari: native HLS cannot send headers; the API accepts the token as a query parameter.
        video.src = `${src}?access_token=${encodeURIComponent(token)}`;
      } else {
        setError("HLS not supported in this browser");
      }
    })();
    return () => {
      cancelled = true;
      hls?.destroy();
      hlsRef.current = null;
    };
  }, [src, getToken]);

  // Restore the last position per user and browser.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onLoaded = () => {
      setLength(video.duration);
      try {
        const saved = Number(window.localStorage.getItem(positionKey));
        if (saved > 5 && saved < video.duration - 5) video.currentTime = saved;
      } catch {
        // ignore
      }
    };
    video.addEventListener("loadedmetadata", onLoaded);
    return () => video.removeEventListener("loadedmetadata", onLoaded);
  }, [positionKey]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = Number(speed) || 1;
  }, [speed]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTimeUpdate = () => {
      setTime(video.currentTime);
      onTime?.(video.currentTime);
      try {
        window.localStorage.setItem(positionKey, String(Math.floor(video.currentTime)));
      } catch {
        // ignore
      }
      if (video.buffered.length) setBuffered(video.buffered.end(video.buffered.length - 1));
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    video.addEventListener("timeupdate", onTimeUpdate);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    return () => {
      video.removeEventListener("timeupdate", onTimeUpdate);
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
    };
  }, [onTime, positionKey]);

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  }

  function stepPhase(direction: 1 | -1) {
    const v = videoRef.current;
    if (!v || phaseBoundaries.length === 0) return;
    const now = v.currentTime;
    const target = direction === 1 ? phaseBoundaries.find((b) => b > now + 0.5) : [...phaseBoundaries].reverse().find((b) => b < now - 0.5);
    if (target !== undefined) seek(target);
  }

  // Keyboard shortcuts: space, J K L, arrows, comma and period, [ and ], F, M.
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      const v = videoRef.current;
      if (!v) return;
      switch (e.key) {
        case " ":
        case "k":
        case "K":
          e.preventDefault();
          togglePlay();
          break;
        case "j":
        case "J":
          seek(v.currentTime - 10);
          break;
        case "l":
        case "L":
          seek(v.currentTime + 10);
          break;
        case "ArrowLeft":
          seek(v.currentTime - 5);
          break;
        case "ArrowRight":
          seek(v.currentTime + 5);
          break;
        case ",":
          v.pause();
          seek(v.currentTime - FRAME_S);
          break;
        case ".":
          v.pause();
          seek(v.currentTime + FRAME_S);
          break;
        case "[":
          stepPhase(-1);
          break;
        case "]":
          stepPhase(1);
          break;
        case "f":
        case "F":
          void toggleFullscreen();
          break;
        case "m":
        case "M":
          v.muted = !v.muted;
          setMuted(v.muted);
          break;
        default:
          return;
      }
    };
    wrap.addEventListener("keydown", onKey);
    return () => wrap.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phaseBoundaries, seek]);

  async function toggleFullscreen() {
    if (!wrapRef.current) return;
    if (document.fullscreenElement) await document.exitFullscreen();
    else await wrapRef.current.requestFullscreen();
  }

  function scrubFromEvent(e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    return { ratio, x: e.clientX - rect.left };
  }

  const pct = length > 0 ? (time / length) * 100 : 0;
  const bufferedPct = length > 0 ? (buffered / length) * 100 : 0;

  const tile = (() => {
    if (!sprite || !hover) return null;
    const i = Math.min(sprite.index.count - 1, Math.floor(hover.t / sprite.index.interval_s));
    if (i < 0) return null;
    return {
      x: (i % sprite.index.columns) * sprite.index.tile_width,
      y: Math.floor(i / sprite.index.columns) * sprite.index.tile_height,
    };
  })();

  return (
    <div
      ref={wrapRef}
      tabIndex={0}
      className={cn("group relative flex flex-col rounded-panel border border-border bg-black outline-none focus-visible:ring-2 focus-visible:ring-accent", fullscreen && "rounded-none border-0")}
      aria-label={t("video.shortcuts")}
    >
      <div className="relative aspect-video w-full bg-black" onClick={togglePlay} onDoubleClick={() => void toggleFullscreen()}>
        <video ref={videoRef} className="size-full" playsInline preload="metadata" />
        {error ? (
          <div className="absolute inset-0 flex items-center justify-center bg-black/80 p-6 text-center text-sm text-white">{error}</div>
        ) : null}
      </div>

      <div className="flex flex-col gap-1 bg-[#0F1110] px-3 pb-2 pt-2 text-[#ECEEEB]">
        <div
          className="relative h-3 cursor-pointer"
          onMouseMove={(e) => {
            const { ratio, x } = scrubFromEvent(e);
            setHover({ x, t: ratio * length });
          }}
          onMouseLeave={() => setHover(null)}
          onClick={(e) => {
            e.stopPropagation();
            seek(scrubFromEvent(e).ratio * length);
          }}
          role="slider"
          aria-label="Position"
          aria-valuemin={0}
          aria-valuemax={Math.round(length)}
          aria-valuenow={Math.round(time)}
        >
          <div className="absolute inset-x-0 top-1 h-1 rounded-full bg-white/15">
            <div className="absolute inset-y-0 left-0 rounded-full bg-white/25" style={{ width: `${bufferedPct}%` }} />
            <div className="absolute inset-y-0 left-0 rounded-full bg-[#6FBF8F]" style={{ width: `${pct}%` }} />
          </div>
          <div className="absolute top-0.5 size-2 -translate-x-1/2 rounded-full bg-[#6FBF8F]" style={{ left: `${pct}%` }} />
          {hover ? (
            <div className="pointer-events-none absolute bottom-4 -translate-x-1/2 rounded-control border border-white/15 bg-[#171A18] p-1 text-center" style={{ left: hover.x }}>
              {sprite && tile ? (
                <div
                  className="mb-1"
                  style={{
                    width: sprite.index.tile_width,
                    height: sprite.index.tile_height,
                    backgroundImage: `url(${sprite.url})`,
                    backgroundPosition: `-${tile.x}px -${tile.y}px`,
                  }}
                />
              ) : null}
              <div className="font-mono text-[11px] tabular">{formatTimestamp(hover.t)}</div>
            </div>
          ) : null}
        </div>

        {timelineExtras}

        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="text-inherit hover:bg-white/10" onClick={togglePlay} aria-label={playing ? t("video.pause") : t("video.play")}>
            {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="text-inherit hover:bg-white/10"
            onClick={() => {
              const v = videoRef.current;
              if (!v) return;
              v.muted = !v.muted;
              setMuted(v.muted);
            }}
            aria-label={muted ? t("video.unmute") : t("video.mute")}
          >
            {muted ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
          </Button>
          <span className="ml-1 font-mono text-xs tabular">
            {formatTimestamp(time)} / {formatTimestamp(length)}
          </span>
          <div className="ml-auto flex items-center gap-1">
            <select
              aria-label={t("video.speed")}
              className="h-7 rounded-control border border-white/15 bg-transparent px-1 text-xs"
              value={speed}
              onChange={(e) => setSpeed(e.target.value)}
            >
              {SPEEDS.map((s) => (
                <option key={s} value={String(s)} className="text-black">
                  {s}×
                </option>
              ))}
            </select>
            {levels.length > 1 ? (
              <select
                aria-label={t("video.quality")}
                className="h-7 rounded-control border border-white/15 bg-transparent px-1 text-xs"
                value={level}
                onChange={(e) => {
                  const next = Number(e.target.value);
                  setLevel(next);
                  if (hlsRef.current) hlsRef.current.currentLevel = next;
                }}
              >
                <option value={-1} className="text-black">
                  {t("video.auto")}
                </option>
                {levels.map((l, i) => (
                  <option key={i} value={i} className="text-black">
                    {l.height}p
                  </option>
                ))}
              </select>
            ) : null}
            <Button variant="ghost" size="icon" className="text-inherit hover:bg-white/10" onClick={() => void toggleFullscreen()} aria-label={t("video.fullscreen")}>
              {fullscreen ? <Minimize aria-hidden /> : <Maximize aria-hidden />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
});
