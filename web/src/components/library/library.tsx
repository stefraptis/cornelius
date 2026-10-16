"use client";

import { LayoutGrid, List, RefreshCw, Video as VideoIcon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { UploadDialog } from "@/components/library/upload-dialog";
import { Button } from "@/components/ui/button";
import { Chip, type ChipTone, EmptyState, PageHeader } from "@/components/ui/display";
import { Input, Select } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { type Procedure, type StorageUsage, type Video, type VideoListParams, videosApi } from "@/lib/api";
import { t } from "@/lib/i18n";
import { useLocalPref } from "@/lib/local-pref";
import { createClient } from "@/lib/supabase/client";
import { cn, formatBytes, formatTimestamp } from "@/lib/utils";

const STATUS_TONE: Record<Video["status"], ChipTone> = {
  uploading: "neutral",
  processing: "neutral",
  ready: "accent",
  analyzing: "accent",
  analyzed: "accent",
  failed: "danger",
};

const SORTS = ["created_desc", "created_asc", "operation_desc", "operation_asc", "duration_desc", "duration_asc"] as const;
const SORT_KEYS: Record<(typeof SORTS)[number], string> = {
  created_desc: "library.sortCreatedDesc",
  created_asc: "library.sortCreatedAsc",
  operation_desc: "library.sortOperationDesc",
  operation_asc: "library.sortOperationAsc",
  duration_desc: "library.sortDurationDesc",
  duration_asc: "library.sortDurationAsc",
};

async function token(): Promise<string | null> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ?? null;
}

export function StatusChip({ status }: { status: Video["status"] }) {
  return <Chip tone={STATUS_TONE[status]}>{t(`status.${status}`)}</Chip>;
}

function StorageMeter({ usage }: { usage: StorageUsage | null }) {
  if (!usage) return null;
  const pct = usage.quota_bytes > 0 ? Math.min(100, (usage.used_bytes / usage.quota_bytes) * 100) : 0;
  return (
    <div className="min-w-48 text-xs text-text-muted" aria-label={t("library.storage")}>
      <div className="flex justify-between">
        <span>{t("library.storage")}</span>
        <span className="font-mono tabular">
          {t("library.storageOf", { used: formatBytes(usage.used_bytes), quota: formatBytes(usage.quota_bytes) })}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface" aria-hidden>
        <div className={cn("h-1.5 rounded-full", pct > 90 ? "bg-warning" : "bg-accent")} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function Library({
  initialVideos,
  initialUsage,
  procedures,
}: {
  initialVideos: Video[];
  initialUsage: StorageUsage | null;
  procedures: Procedure[];
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [videos, setVideos] = useState(initialVideos);
  const [usage, setUsage] = useState(initialUsage);
  const [view, setView] = useLocalPref("cornelius.library.view", "grid");
  const [scope, setScope] = useState<"mine" | "shared">((searchParams.get("scope") as "mine" | "shared") || "mine");
  const [q, setQ] = useState("");
  const [procedure, setProcedure] = useState("");
  const [status, setStatus] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sort, setSort] = useState<(typeof SORTS)[number]>("created_desc");
  const [loading, setLoading] = useState(false);

  const params = useMemo<VideoListParams>(
    () => ({ scope, q: q || undefined, procedure: procedure || undefined, status: status || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined, sort }),
    [scope, q, procedure, status, dateFrom, dateTo, sort],
  );

  const reload = useCallback(async () => {
    const access = await token();
    if (!access) return router.replace("/login");
    setLoading(true);
    try {
      const [list, storage] = await Promise.all([videosApi.list(access, params), videosApi.storage(access)]);
      setVideos(list);
      setUsage(storage);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
    } finally {
      setLoading(false);
    }
  }, [params, router]);

  // Reload when filters change (debounced for typing).
  useEffect(() => {
    const handle = setTimeout(() => void reload(), 250);
    return () => clearTimeout(handle);
  }, [reload]);

  // Poll while something is still processing.
  const busy = videos.some((v) => ["uploading", "processing", "analyzing"].includes(v.status));
  useEffect(() => {
    if (!busy) return;
    const handle = setInterval(() => void reload(), 8000);
    return () => clearInterval(handle);
  }, [busy, reload]);

  const uploadButton = <UploadDialog procedures={procedures} onUploaded={() => void reload()} />;

  return (
    <>
      <PageHeader
        title={t("library.title")}
        actions={
          <>
            <StorageMeter usage={usage} />
            {uploadButton}
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={scope} onValueChange={(v) => setScope(v as "mine" | "shared")}>
          <TabsList>
            <TabsTrigger value="mine">{t("library.myVideos")}</TabsTrigger>
            <TabsTrigger value="shared">{t("library.sharedWithMe")}</TabsTrigger>
          </TabsList>
        </Tabs>
        <Input className="w-56" placeholder={t("library.search")} value={q} onChange={(e) => setQ(e.target.value)} aria-label={t("library.search")} />
        <Select className="w-auto" value={procedure} onChange={(e) => setProcedure(e.target.value)} aria-label={t("upload.procedure")}>
          <option value="">{t("library.allProcedures")}</option>
          {procedures.map((p) => (
            <option key={p.code} value={p.code}>
              {p.name}
            </option>
          ))}
        </Select>
        <Select className="w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label={t("library.columns.status")}>
          <option value="">{t("library.allStatuses")}</option>
          {(["uploading", "processing", "ready", "analyzing", "analyzed", "failed"] as const).map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </Select>
        <Input type="date" className="w-auto" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} aria-label={t("library.from")} />
        <Input type="date" className="w-auto" value={dateTo} onChange={(e) => setDateTo(e.target.value)} aria-label={t("library.to")} />
        <Select className="w-auto" value={sort} onChange={(e) => setSort(e.target.value as (typeof SORTS)[number])} aria-label={t("library.sort")}>
          {SORTS.map((s) => (
            <option key={s} value={s}>
              {t(SORT_KEYS[s] as Parameters<typeof t>[0])}
            </option>
          ))}
        </Select>
        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={() => void reload()} aria-label={t("common.retry")} loading={loading}>
            {!loading ? <RefreshCw aria-hidden /> : null}
          </Button>
          <Button variant={view === "grid" ? "secondary" : "ghost"} size="icon" onClick={() => setView("grid")} aria-label={t("library.gridView")}>
            <LayoutGrid aria-hidden />
          </Button>
          <Button variant={view === "list" ? "secondary" : "ghost"} size="icon" onClick={() => setView("list")} aria-label={t("library.listView")}>
            <List aria-hidden />
          </Button>
        </div>
      </div>

      <div className="mt-6">
        {videos.length === 0 ? (
          q || procedure || status || dateFrom || dateTo ? (
            <EmptyState icon={VideoIcon} title={t("library.noResults")} />
          ) : (
            <EmptyState icon={VideoIcon} title={t("library.emptyTitle")} body={t("library.emptyBody")} action={uploadButton} />
          )
        ) : view === "list" ? (
          <VideoTable videos={videos} />
        ) : (
          <VideoGrid videos={videos} />
        )}
        {busy ? <p className="mt-4 text-xs text-text-muted">{t("library.processingHint")}</p> : null}
      </div>
    </>
  );
}

function Poster({ video, className }: { video: Video; className?: string }) {
  return (
    <div className={cn("relative aspect-video w-full overflow-hidden rounded-control bg-surface", className)}>
      {video.poster_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={video.poster_url} alt="" className="size-full object-cover" loading="lazy" />
      ) : (
        <div className="flex size-full items-center justify-center text-text-muted">
          <VideoIcon className="size-6" strokeWidth={1.5} aria-hidden />
        </div>
      )}
      {video.duration_s ? (
        <span className="absolute bottom-1.5 right-1.5 rounded-[4px] bg-black/70 px-1.5 py-0.5 font-mono text-[11px] tabular text-white">
          {formatTimestamp(video.duration_s)}
        </span>
      ) : null}
    </div>
  );
}

function VideoGrid({ videos }: { videos: Video[] }) {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {videos.map((v) => (
        <li key={v.id}>
          <Link href={`/videos/${v.id}`} className="group block rounded-panel border border-border bg-bg p-3 transition-colors hover:bg-surface">
            <Poster video={v} />
            <div className="mt-3 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{v.title}</div>
                <div className="mt-0.5 truncate text-xs text-text-muted">
                  {v.procedure_name}
                  {v.operation_date ? `, ${v.operation_date}` : ""}
                </div>
              </div>
              <StatusChip status={v.status} />
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function VideoTable({ videos }: { videos: Video[] }) {
  return (
    <div className="overflow-x-auto rounded-panel border border-border">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface text-left text-xs uppercase tracking-wide text-text-muted">
          <tr>
            <th className="px-4 py-2 font-medium">{t("library.columns.title")}</th>
            <th className="px-4 py-2 font-medium">{t("library.columns.procedure")}</th>
            <th className="px-4 py-2 font-medium">{t("library.columns.operationDate")}</th>
            <th className="px-4 py-2 font-medium">{t("library.columns.duration")}</th>
            <th className="px-4 py-2 font-medium">{t("library.columns.status")}</th>
            <th className="px-4 py-2 font-medium">{t("library.columns.uploaded")}</th>
          </tr>
        </thead>
        <tbody>
          {videos.map((v) => (
            <tr key={v.id} className="border-t border-border hover:bg-surface">
              <td className="px-4 py-2">
                <Link href={`/videos/${v.id}`} className="font-medium hover:underline">
                  {v.title}
                </Link>
              </td>
              <td className="px-4 py-2 text-text-muted">{v.procedure_name}</td>
              <td className="px-4 py-2 font-mono tabular text-text-muted">{v.operation_date ?? ""}</td>
              <td className="px-4 py-2 font-mono tabular">{v.duration_s ? formatTimestamp(v.duration_s) : ""}</td>
              <td className="px-4 py-2">
                <StatusChip status={v.status} />
              </td>
              <td className="px-4 py-2 font-mono tabular text-text-muted">{new Date(v.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
