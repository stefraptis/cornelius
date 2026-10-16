"use client";

import { Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/primitives";
import type { Procedure } from "@/lib/api";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";
import { findResumable, MultipartUploader, type UploadProgress } from "@/lib/uploader";
import { track } from "@/lib/usage";
import { cn, formatBytes } from "@/lib/utils";

const MAX_GB = 20;
const EXTENSIONS = ["mp4", "mov", "mkv", "avi"];

async function accessToken(): Promise<string> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  if (!session) throw new Error("Signed out");
  return session.access_token;
}

export function UploadDialog({
  procedures,
  onUploaded,
  trigger,
}: {
  procedures: Procedure[];
  onUploaded?: (videoId: string) => void;
  trigger?: React.ReactNode;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [procedure, setProcedure] = useState(procedures[0]?.code ?? "lc");
  const [operationDate, setOperationDate] = useState("");
  const [analyze, setAnalyze] = useState(true);
  const [consent, setConsent] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const uploader = useRef<MultipartUploader | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = procedures.find((p) => p.code === procedure);
  const resumable = file ? findResumable(file) : null;
  const uploading = progress !== null && !["done", "error", "aborted"].includes(progress.phase);

  useEffect(() => {
    if (!uploading) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [uploading]);

  function pick(candidate: File | null) {
    setFileError(null);
    if (!candidate) return setFile(null);
    const ext = candidate.name.split(".").pop()?.toLowerCase() ?? "";
    if (!EXTENSIONS.includes(ext)) {
      setFileError(t("upload.badType"));
      return setFile(null);
    }
    if (candidate.size > MAX_GB * 1e9) {
      setFileError(t("upload.tooLarge", { max: MAX_GB }));
      return setFile(null);
    }
    setFile(candidate);
    if (!title) setTitle(candidate.name.replace(/\.[^.]+$/, ""));
  }

  async function start(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !consent) return;
    const up = new MultipartUploader(
      file,
      {
        title: title.trim() || file.name,
        procedure_code: procedure,
        operation_date: operationDate || null,
        request_analysis: analyze && Boolean(selected?.analysis_enabled),
      },
      accessToken,
    );
    uploader.current = up;
    up.onProgress(setProgress);
    setProgress({ uploadedBytes: 0, totalBytes: file.size, partsDone: 0, partCount: 0, phase: "starting" });
    track("upload.start", { size_bytes: file.size, procedure });
    try {
      const { video_id } = await up.run();
      setVideoId(video_id);
      track("upload.done", { size_bytes: file.size });
      onUploaded?.(video_id);
      router.refresh();
    } catch {
      // progress already carries the error or abort state
    }
  }

  async function cancel() {
    await uploader.current?.cancel();
    setProgress((p) => (p ? { ...p, phase: "aborted" } : p));
  }

  function reset() {
    setFile(null);
    setTitle("");
    setOperationDate("");
    setConsent(false);
    setProgress(null);
    setVideoId(null);
    uploader.current = null;
  }

  function onOpenChange(next: boolean) {
    if (!next && uploading) return; // keep the dialog while bytes are in flight
    setOpen(next);
    if (!next) reset();
  }

  const pct = progress && progress.totalBytes > 0 ? Math.round((progress.uploadedBytes / progress.totalBytes) * 100) : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button>
            <Upload aria-hidden /> {t("library.upload")}
          </Button>
        )}
      </DialogTrigger>
      <DialogContent title={t("upload.title")} description={t("upload.intro")} className="w-[min(92vw,560px)]">
        {progress ? (
          <div className="flex flex-col gap-4">
            <div>
              <div className="flex items-baseline justify-between text-sm">
                <span className="truncate font-medium">{file?.name}</span>
                <span className="ml-3 shrink-0 font-mono text-xs tabular text-text-muted">{pct}%</span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-surface" aria-hidden>
                <div className="h-2 bg-accent transition-[width] duration-200" style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-2 text-xs text-text-muted" role="status">
                {progress.phase === "uploading"
                  ? t("upload.progress", { done: formatBytes(progress.uploadedBytes), total: formatBytes(progress.totalBytes) }) +
                    (progress.partCount > 1 ? `, ${t("upload.parts", { n: Math.min(progress.partsDone + 1, progress.partCount), count: progress.partCount })}` : "")
                  : null}
                {progress.phase === "starting" ? t("common.loading") : null}
                {progress.phase === "completing" ? t("upload.completing") : null}
                {progress.phase === "done" ? t("upload.done") : null}
                {progress.phase === "aborted" ? t("upload.aborted") : null}
                {progress.phase === "error" ? t("upload.failed", { message: progress.message ?? "" }) : null}
                {progress.message && progress.phase === "uploading" ? ` ${progress.message}` : null}
              </p>
            </div>
            <div className="flex justify-end gap-2">
              {uploading ? (
                <Button variant="ghost" onClick={cancel}>
                  {t("upload.cancel")}
                </Button>
              ) : (
                <>
                  <Button variant="ghost" onClick={reset}>
                    {t("upload.another")}
                  </Button>
                  {videoId ? (
                    <Button asChild>
                      <Link href={`/videos/${videoId}`}>{t("upload.goToVideo")}</Link>
                    </Button>
                  ) : (
                    <Button onClick={() => onOpenChange(false)}>{t("upload.close")}</Button>
                  )}
                </>
              )}
            </div>
          </div>
        ) : (
          <form onSubmit={start} className="flex flex-col gap-4">
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                pick(e.dataTransfer.files[0] ?? null);
              }}
              className={cn(
                "flex flex-col items-center justify-center gap-2 rounded-panel border border-dashed px-4 py-6 text-sm",
                dragging ? "border-accent bg-surface" : "border-border",
                fileError && "border-danger",
              )}
            >
              <input
                ref={inputRef}
                type="file"
                accept=".mp4,.mov,.mkv,.avi,video/mp4,video/quicktime,video/x-matroska,video/x-msvideo"
                className="sr-only"
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
              {file ? (
                <>
                  <span className="font-medium">{file.name}</span>
                  <span className="font-mono text-xs tabular text-text-muted">{formatBytes(file.size)}</span>
                  {resumable ? <span className="text-xs text-accent">{t("upload.resumeNotice")}</span> : null}
                </>
              ) : (
                <>
                  <Upload className="size-6 text-text-muted" aria-hidden />
                  <span className="text-text-muted">{t("upload.dropHere")}</span>
                </>
              )}
              <Button type="button" variant="secondary" size="sm" onClick={() => inputRef.current?.click()}>
                {t("upload.chooseFile")}
              </Button>
              <span className="text-xs text-text-muted">{fileError ?? t("upload.fileHint", { max: MAX_GB })}</span>
            </div>

            <Field label={t("upload.videoTitle")} htmlFor="upload-title">
              <Input
                id="upload-title"
                required
                maxLength={200}
                placeholder={t("upload.videoTitlePlaceholder")}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("upload.procedure")} htmlFor="upload-procedure">
                <Select id="upload-procedure" value={procedure} onChange={(e) => setProcedure(e.target.value)}>
                  {procedures.map((p) => (
                    <option key={p.code} value={p.code}>
                      {p.name}
                      {p.analysis_enabled ? "" : ` ${t("upload.comingSoonSuffix")}`}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label={`${t("upload.operationDate")} (${t("common.optional").toLowerCase()})`} htmlFor="upload-date">
                <Input id="upload-date" type="date" value={operationDate} onChange={(e) => setOperationDate(e.target.value)} />
              </Field>
            </div>
            <label className={cn("flex items-start gap-2 text-sm", !selected?.analysis_enabled && "opacity-60")}>
              <Checkbox
                checked={analyze && Boolean(selected?.analysis_enabled)}
                disabled={!selected?.analysis_enabled}
                onChange={(e) => setAnalyze(e.target.checked)}
              />
              <span>{t("upload.requestAnalysis")}</span>
            </label>
            <label className="flex items-start gap-2 text-sm">
              <Checkbox checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
              <span>{t("upload.consent")}</span>
            </label>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={!file || !consent || !title.trim()}>
                {t("upload.start")}
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
