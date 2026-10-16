/**
 * Typed client for the Cornelius API. The browser talks to the API only for
 * metadata and permissions; video bytes never pass through it.
 */
import { env } from "@/lib/env";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export type Profile = {
  id: string;
  full_name: string;
  title: string | null;
  specialty: string | null;
  locale: string;
  created_at: string;
  updated_at: string;
};

export type Workspace = {
  id: string;
  kind: "personal" | "team";
  name: string;
  team_id: string | null;
  storage_quota_gb: number;
};

export type Me = {
  user_id: string;
  email: string | null;
  second_factor: boolean;
  profile: Profile;
  workspaces: Workspace[];
  teams: { team_id: string; team_name: string; org_id: string | null; role: string }[];
  organizations: { org_id: string; org_name: string; role: string }[];
  platform_admin: boolean;
};

export type FeedbackCategory = "bug" | "idea" | "question" | "other";

export type UsageEvent = {
  event: string;
  page?: string;
  properties?: Record<string, string | number | boolean | null>;
  duration_ms?: number;
  session_id?: string;
  at?: string;
};

export type UsageSummary = {
  days: number;
  total_users: number;
  active_users: number;
  total_events: number;
  feedback_new: number;
  daily: { day: string; events: number; users: number }[];
  by_event: { event: string; events: number; users: number }[];
  top_users: { user_id: string | null; full_name: string | null; events: number; last_seen: string | null }[];
};

export type FeedbackRow = {
  id: string;
  user_id: string | null;
  full_name: string | null;
  category: FeedbackCategory;
  message: string;
  page_url: string | null;
  status: "new" | "seen" | "planned" | "done" | "closed";
  admin_note: string | null;
  created_at: string;
};

export type Label = { code: string; name: string; color: string; order: number };

export type ModelVersion = {
  id: string;
  name: string;
  architecture: string | null;
  phase_labels: Label[];
  tool_labels: Label[];
  metrics: Record<string, unknown>;
  thresholds: Record<string, unknown>;
};

export type Procedure = {
  code: string;
  name: string;
  modality: string;
  analysis_enabled: boolean;
  model_version: ModelVersion | null;
};

async function request<T>(
  path: string,
  token: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  headers.set("Accept", "application/json");
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    headers,
    body,
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  me: (token: string) => request<Me>("/me", token),
  updateProfile: (token: string, changes: Partial<Pick<Profile, "full_name" | "title" | "specialty" | "locale">>) =>
    request<Profile>("/me/profile", token, { method: "PATCH", json: changes }),
  procedures: (token: string) => request<Procedure[]>("/procedures", token),
  sendFeedback: (
    token: string,
    body: { category: FeedbackCategory; message: string; page_url?: string; app_version?: string },
  ) => request<{ id: string }>("/feedback", token, { method: "POST", json: body }),
  sendUsage: (token: string, events: UsageEvent[]) =>
    request<{ accepted: number }>("/usage/events", token, { method: "POST", json: { events } }),
  adminUsage: (token: string, days: number) => request<UsageSummary>(`/admin/usage?days=${days}`, token),
  adminFeedback: (token: string) => request<FeedbackRow[]>("/admin/feedback", token),
  adminUpdateFeedback: (token: string, id: string, changes: { status?: string; admin_note?: string }) =>
    request<FeedbackRow>(`/admin/feedback/${id}`, token, { method: "PATCH", json: changes }),
};

export type VideoStatus = "uploading" | "processing" | "ready" | "analyzing" | "analyzed" | "failed";

export type Video = {
  id: string;
  owner_user_id: string;
  workspace_id: string;
  procedure_code: string;
  procedure_name: string | null;
  title: string;
  operation_date: string | null;
  duration_s: number | null;
  status: VideoStatus;
  size_bytes: number | null;
  analysis_requested: boolean;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  poster_url: string | null;
  is_owner: boolean;
  permission: string | null;
};

export type StorageUsage = { used_bytes: number; quota_bytes: number; videos: number };

export type VideoListParams = {
  scope?: "mine" | "shared" | "all";
  q?: string;
  procedure?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  sort?: string;
};

export const videosApi = {
  list: (token: string, params: VideoListParams = {}) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v) qs.set(k, String(v));
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<Video[]>(`/videos${suffix}`, token);
  },
  get: (token: string, id: string) => request<Video>(`/videos/${id}`, token),
  update: (token: string, id: string, changes: { title?: string; operation_date?: string | null }) =>
    request<Video>(`/videos/${id}`, token, { method: "PATCH", json: changes }),
  remove: (token: string, id: string) => request<void>(`/videos/${id}`, token, { method: "DELETE" }),
  storage: (token: string) => request<StorageUsage>("/videos/storage", token),
  asset: (token: string, id: string, kind: "poster" | "sprite" | "proxy" | "original") =>
    request<{ url: string }>(`/videos/${id}/assets/${kind}`, token),
  spriteIndex: (token: string, id: string) =>
    request<{ interval_s: number; tile_width: number; tile_height: number; columns: number; count: number }>(
      `/videos/${id}/sprite-index`,
      token,
    ),
  streamUrl: (id: string) => `${env.apiBaseUrl}/videos/${id}/stream.m3u8`,
};

export type Consent = { terms_version: string | null; privacy_version: string | null; accepted_at: string | null };

export const privacyApi = {
  consent: (token: string) => request<Consent>("/me/consent", token),
  accept: (token: string, terms_version: string, privacy_version: string) =>
    request<Consent>("/me/consent", token, { method: "POST", json: { terms_version, privacy_version } }),
  deleteAccount: (token: string, confirm_email: string) =>
    request<{ status: string }>("/me/delete", token, { method: "POST", json: { confirm_email } }),
  exportUrl: () => `${env.apiBaseUrl}/me/export`,
};

export const APP_VERSION = "0.1.0";
