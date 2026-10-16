"use client";

import { ArrowLeft, Download, Pencil, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { StatusChip } from "@/components/library/library";
import { type PlayerHandle, type SpriteIndex, VideoPlayer } from "@/components/player/video-player";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/display";
import { Dialog, DialogContent, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { Field, Input } from "@/components/ui/input";
import { type Video, videosApi } from "@/lib/api";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";
import { track } from "@/lib/usage";
import { formatBytes, formatTimestamp } from "@/lib/utils";

async function token(): Promise<string | null> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ?? null;
}

export function VideoPage({ initial, spriteUrl, spriteIndex }: { initial: Video; spriteUrl: string | null; spriteIndex: SpriteIndex | null }) {
  const router = useRouter();
  const [video, setVideo] = useState(initial);
  const player = useRef<PlayerHandle>(null);
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [title, setTitle] = useState(initial.title);
  const [busy, setBusy] = useState(false);
  const playable = ["ready", "analyzing", "analyzed"].includes(video.status);

  const refresh = useCallback(async () => {
    const access = await token();
    if (!access) return;
    try {
      setVideo(await videosApi.get(access, video.id));
    } catch {
      // keep the last known state
    }
  }, [video.id]);

  useEffect(() => {
    if (!["uploading", "processing", "analyzing"].includes(video.status)) return;
    const handle = setInterval(() => void refresh(), 8000);
    return () => clearInterval(handle);
  }, [video.status, refresh]);

  useEffect(() => {
    track("video.open", { status: video.status });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function rename(event: React.FormEvent) {
    event.preventDefault();
    const access = await token();
    if (!access) return;
    setBusy(true);
    try {
      setVideo(await videosApi.update(access, video.id, { title: title.trim() }));
      setRenameOpen(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    const access = await token();
    if (!access) return;
    setBusy(true);
    try {
      await videosApi.remove(access, video.id);
      toast.success(t("library.deleted"));
      router.replace("/library");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
      setBusy(false);
    }
  }

  async function downloadOriginal() {
    const access = await token();
    if (!access) return;
    try {
      const { url } = await videosApi.asset(access, video.id, "original");
      window.open(url, "_blank", "noopener");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
    }
  }

  const duplicate = video.last_error?.startsWith("Duplicate");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button asChild variant="ghost" size="sm">
          <Link href="/library">
            <ArrowLeft aria-hidden /> {t("video.back")}
          </Link>
        </Button>
        <h1 className="min-w-0 flex-1 truncate text-lg font-semibold tracking-tight">{video.title}</h1>
        <StatusChip status={video.status} />
        {video.is_owner ? (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => setRenameOpen(true)}>
              <Pencil aria-hidden /> {t("video.rename")}
            </Button>
            <Button variant="ghost" size="sm" onClick={downloadOriginal}>
              <Download aria-hidden /> {t("video.downloadOriginal")}
            </Button>
            <Button variant="ghost" size="sm" className="text-danger" onClick={() => setDeleteOpen(true)}>
              <Trash2 aria-hidden /> {t("video.delete")}
            </Button>
          </div>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,65fr)_minmax(320px,35fr)]">
        <div className="min-w-0">
          {playable ? (
            <VideoPlayer
              ref={player}
              videoId={video.id}
              src={videosApi.streamUrl(video.id)}
              getToken={token}
              duration={video.duration_s}
              sprite={spriteUrl && spriteIndex ? { url: spriteUrl, index: spriteIndex } : null}
            />
          ) : (
            <div className="flex aspect-video items-center justify-center rounded-panel border border-border bg-surface p-6 text-center text-sm text-text-muted">
              {video.status === "failed" ? (
                <div>
                  <p className="text-danger">{t("video.failed")}</p>
                  {video.last_error ? <p className="mt-1 font-mono text-xs">{video.last_error}</p> : null}
                </div>
              ) : (
                t("video.processing")
              )}
            </div>
          )}
          {duplicate ? <p className="mt-2 text-xs text-warning">{t("video.duplicate")}</p> : null}
          <p className="mt-2 text-xs text-text-muted">{t("video.shortcuts")}</p>
        </div>

        <Panel className="min-w-0">
          <Tabs defaultValue="overview">
            <TabsList className="w-full px-2">
              <TabsTrigger value="overview">{t("video.overview")}</TabsTrigger>
              <TabsTrigger value="analytics" disabled>
                {t("video.analytics")}
              </TabsTrigger>
              <TabsTrigger value="comments" disabled>
                {t("video.comments")}
              </TabsTrigger>
              <TabsTrigger value="quiz" disabled>
                {t("video.quiz")}
              </TabsTrigger>
              <TabsTrigger value="ask" disabled>
                {t("video.ask")}
              </TabsTrigger>
              <TabsTrigger value="report" disabled>
                {t("video.report")}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="overview" className="px-4 pb-4">
              <h2 className="text-xs font-medium uppercase tracking-wide text-text-muted">{t("video.details")}</h2>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
                <dt className="text-text-muted">{t("video.procedure")}</dt>
                <dd>{video.procedure_name}</dd>
                <dt className="text-text-muted">{t("video.operationDate")}</dt>
                <dd className="font-mono tabular">{video.operation_date ?? "-"}</dd>
                <dt className="text-text-muted">{t("video.duration")}</dt>
                <dd className="font-mono tabular">{video.duration_s ? formatTimestamp(video.duration_s) : "-"}</dd>
                <dt className="text-text-muted">{t("video.size")}</dt>
                <dd className="font-mono tabular">{video.size_bytes ? formatBytes(video.size_bytes) : "-"}</dd>
                <dt className="text-text-muted">{t("video.uploaded")}</dt>
                <dd className="font-mono tabular">{new Date(video.created_at).toLocaleString()}</dd>
              </dl>
              <p className="mt-4 text-sm text-text-muted">
                {video.status === "analyzed"
                  ? null
                  : video.analysis_requested
                    ? t("video.analysisPending")
                    : t("video.analysisComingSoon")}
              </p>
            </TabsContent>
          </Tabs>
        </Panel>
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent title={t("video.rename")}>
          <form onSubmit={rename} className="flex flex-col gap-4">
            <Field label={t("upload.videoTitle")} htmlFor="rename-title">
              <Input id="rename-title" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={200} autoFocus />
            </Field>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setRenameOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" loading={busy}>
                {t("common.save")}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent title={t("library.deleteTitle")} description={t("library.deleteBody")}>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button variant="danger" onClick={remove} loading={busy}>
              {t("common.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
