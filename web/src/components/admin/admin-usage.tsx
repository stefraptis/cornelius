"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Chip, type ChipTone, PageHeader, Panel, PanelHeader, StatTile } from "@/components/ui/display";
import { Select } from "@/components/ui/input";
import { api, type FeedbackRow, type UsageSummary } from "@/lib/api";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const STATUSES: FeedbackRow["status"][] = ["new", "seen", "planned", "done", "closed"];
const STATUS_TONE: Record<FeedbackRow["status"], ChipTone> = {
  new: "accent",
  seen: "neutral",
  planned: "warning",
  done: "neutral",
  closed: "neutral",
};

function formatDay(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

function formatWhen(iso: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** Horizontal bar with a label and value; the data color is the single accent. */
function BarRow({ label, value, max, sub }: { label: string; value: number; max: number; sub?: string }) {
  const width = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] items-center gap-3 text-sm">
      <span className="truncate font-mono text-xs">{label}</span>
      <span className="h-2 rounded-full bg-surface" aria-hidden>
        <span className="block h-2 rounded-full bg-accent" style={{ width: `${width}%` }} />
      </span>
      <span className="font-mono text-xs tabular text-text-muted">
        {value}
        {sub ? <span className="ml-1">({sub})</span> : null}
      </span>
    </div>
  );
}

export function AdminUsage({ summary, feedback }: { summary: UsageSummary; feedback: FeedbackRow[] }) {
  const router = useRouter();
  const [rows, setRows] = useState(feedback);
  const maxDaily = Math.max(0, ...summary.daily.map((d) => d.events));
  const maxEvent = Math.max(0, ...summary.by_event.map((e) => e.events));

  async function setStatus(id: string, status: FeedbackRow["status"]) {
    const {
      data: { session },
    } = await createClient().auth.getSession();
    if (!session) return;
    try {
      const updated = await api.adminUpdateFeedback(session.access_token, id, { status });
      setRows((current) => current.map((r) => (r.id === id ? updated : r)));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
    }
  }

  return (
    <>
      <PageHeader
        title={t("admin.title")}
        description={t("admin.intro", { days: summary.days })}
        actions={
          <div className="flex gap-1">
            {[7, 30, 90].map((d) => (
              <Link
                key={d}
                href={`/admin/usage?days=${d}`}
                className={cn(
                  "rounded-control border px-3 py-1.5 text-sm",
                  d === summary.days ? "border-accent text-accent" : "border-border text-text-muted hover:text-text",
                )}
                onClick={() => router.refresh()}
              >
                {t(d === 7 ? "admin.range7" : d === 30 ? "admin.range30" : "admin.range90")}
              </Link>
            ))}
          </div>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label={t("admin.accounts")} value={summary.total_users} />
        <StatTile label={t("admin.activeUsers")} value={summary.active_users} />
        <StatTile label={t("admin.events")} value={summary.total_events} />
        <StatTile label={t("admin.newFeedback")} value={summary.feedback_new} tone={summary.feedback_new ? "accent" : "neutral"} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel>
          <PanelHeader title={t("admin.daily")} />
          <div className="flex flex-col gap-2 p-5">
            {summary.daily.length === 0 ? (
              <p className="text-sm text-text-muted">0</p>
            ) : (
              summary.daily.map((d) => (
                <BarRow key={d.day} label={formatDay(d.day)} value={d.events} max={maxDaily} sub={`${d.users} ${t("admin.users").toLowerCase()}`} />
              ))
            )}
          </div>
        </Panel>
        <Panel>
          <PanelHeader title={t("admin.byEvent")} />
          <div className="flex flex-col gap-2 p-5">
            {summary.by_event.map((e) => (
              <BarRow key={e.event} label={e.event} value={e.events} max={maxEvent} sub={`${e.users}`} />
            ))}
          </div>
        </Panel>
      </div>

      <Panel className="mt-6">
        <PanelHeader title={t("admin.topUsers")} />
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-text-muted">
            <tr className="border-b border-border">
              <th className="px-5 py-2 font-medium">{t("admin.users")}</th>
              <th className="px-5 py-2 font-medium">{t("admin.events")}</th>
              <th className="px-5 py-2 font-medium">{t("admin.lastSeen")}</th>
            </tr>
          </thead>
          <tbody>
            {summary.top_users.map((u) => (
              <tr key={u.user_id ?? "anon"} className="border-b border-border last:border-0">
                <td className="px-5 py-2">{u.full_name || u.user_id || "?"}</td>
                <td className="px-5 py-2 font-mono tabular">{u.events}</td>
                <td className="px-5 py-2 font-mono tabular text-text-muted">{formatWhen(u.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel className="mt-6">
        <PanelHeader title={t("admin.feedbackList")} />
        {rows.length === 0 ? (
          <p className="p-5 text-sm text-text-muted">{t("admin.noFeedback")}</p>
        ) : (
          <ul className="divide-y divide-border">
            {rows.map((f) => (
              <li key={f.id} className="flex flex-col gap-2 px-5 py-4">
                <div className="flex flex-wrap items-center gap-2 text-xs text-text-muted">
                  <Chip tone={STATUS_TONE[f.status]}>{t(`admin.statuses.${f.status}`)}</Chip>
                  <span>{t(`feedback.categories.${f.category}`)}</span>
                  <span aria-hidden>|</span>
                  <span>{f.full_name || f.user_id || "?"}</span>
                  <span aria-hidden>|</span>
                  <span className="font-mono tabular">{formatWhen(f.created_at)}</span>
                  {f.page_url ? <span className="font-mono">{f.page_url}</span> : null}
                  <Select
                    aria-label={t("admin.status")}
                    className="ml-auto h-7 w-auto text-xs"
                    value={f.status}
                    onChange={(e) => setStatus(f.id, e.target.value as FeedbackRow["status"])}
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {t(`admin.statuses.${s}`)}
                      </option>
                    ))}
                  </Select>
                </div>
                <p className="whitespace-pre-wrap text-sm">{f.message}</p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
