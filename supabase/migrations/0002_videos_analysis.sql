-- 0002 Procedures, videos, jobs, analysis outputs, audit log
-- (Build Guideline, Section 4). Nothing here assumes cholecystectomy: phase
-- and tool names come from model_versions.phase_labels and tool_labels.

-- ---------- enums ----------

create type public.video_status as enum (
  'uploading', 'processing', 'ready', 'analyzing', 'analyzed', 'failed'
);
create type public.share_permission as enum ('view', 'comment', 'annotate');
create type public.job_type as enum ('transcode', 'analyze', 'narrate', 'export', 'purge');
create type public.job_status as enum ('queued', 'running', 'succeeded', 'failed', 'cancelled');
create type public.analysis_status as enum ('queued', 'running', 'completed', 'failed');
create type public.scene_event_type as enum (
  'bleeding', 'blood_in_field', 'smoke', 'idle', 'camera_out'
);

-- ---------- procedure registry ----------

create table public.procedures (
  code text primary key,
  name text not null,
  modality text not null default 'laparoscopic',      -- laparoscopic | robotic | open
  analysis_enabled boolean not null default false,
  model_version_id uuid,                                -- FK added below
  display_order integer not null default 100,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create trigger procedures_updated_at before update on public.procedures
  for each row execute function public.set_updated_at();

-- phase_labels and tool_labels are JSON arrays of
--   {"code": "<model class name>", "name": "<display name>", "color": "#RRGGBB", "order": n}
-- Model class names stay in the database; display names are mapped from here.
create table public.model_versions (
  id uuid primary key default gen_random_uuid(),
  procedure_code text not null references public.procedures (code) on delete cascade,
  name text not null,
  architecture text,
  phase_labels jsonb not null default '[]'::jsonb,
  tool_labels jsonb not null default '[]'::jsonb,
  metrics jsonb not null default '{}'::jsonb,
  thresholds jsonb not null default '{}'::jsonb,
  weights_uri text,
  is_active boolean not null default false,
  created_at timestamptz not null default now(),
  unique (procedure_code, name)
);

alter table public.procedures
  add constraint procedures_model_version_fk
  foreign key (model_version_id) references public.model_versions (id) on delete set null;

-- ---------- videos ----------

create table public.videos (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users (id) on delete cascade,
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  procedure_code text not null references public.procedures (code),
  title text not null,
  operation_date date,
  duration_s numeric(10, 3),
  status public.video_status not null default 'uploading',
  original_key text,
  hls_prefix text,
  thumbnail_key text,
  proxy_key text,
  sprite_key text,
  size_bytes bigint,
  sha256 text,
  upload_id text,                       -- S3 multipart upload id while uploading
  consent_confirmed_at timestamptz,
  analysis_requested boolean not null default false,
  extra_streams jsonb not null default '[]'::jsonb,   -- optional extra streams (kinematics, second camera)
  original_purge_at timestamptz,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);
create index videos_owner_idx on public.videos (owner_user_id) where deleted_at is null;
create index videos_workspace_idx on public.videos (workspace_id) where deleted_at is null;
create index videos_status_idx on public.videos (status);
create trigger videos_updated_at before update on public.videos
  for each row execute function public.set_updated_at();

create table public.video_shares (
  id uuid primary key default gen_random_uuid(),
  video_id uuid not null references public.videos (id) on delete cascade,
  team_id uuid references public.teams (id) on delete cascade,
  org_id uuid references public.organizations (id) on delete cascade,
  permission public.share_permission not null default 'view',
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  constraint video_shares_target check (
    (team_id is not null and org_id is null) or (team_id is null and org_id is not null)
  )
);
create unique index video_shares_team_unique on public.video_shares (video_id, team_id) where team_id is not null;
create unique index video_shares_org_unique on public.video_shares (video_id, org_id) where org_id is not null;
create index video_shares_team_idx on public.video_shares (team_id);
create index video_shares_org_idx on public.video_shares (org_id);

-- ---------- jobs (work queue) ----------

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  type public.job_type not null,
  video_id uuid references public.videos (id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  status public.job_status not null default 'queued',
  attempts integer not null default 0,
  max_attempts integer not null default 3,
  error text,
  run_after timestamptz not null default now(),
  locked_by text,
  locked_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index jobs_queue_idx on public.jobs (status, run_after) where status = 'queued';
create index jobs_video_idx on public.jobs (video_id);
create trigger jobs_updated_at before update on public.jobs
  for each row execute function public.set_updated_at();

-- Claim the next queued job atomically (used by the dispatcher and workers,
-- always with the service role).
create or replace function public.claim_next_job(p_types public.job_type[], p_worker text)
returns setof public.jobs
language plpgsql security definer set search_path = public as $$
declare
  v_id uuid;
begin
  select id into v_id
  from public.jobs
  where status = 'queued' and type = any (p_types) and run_after <= now()
  order by created_at
  for update skip locked
  limit 1;

  if v_id is null then
    return;
  end if;

  return query
  update public.jobs
  set status = 'running', attempts = attempts + 1, locked_by = p_worker,
      locked_at = now(), started_at = coalesce(started_at, now())
  where id = v_id
  returning *;
end
$$;

-- ---------- analyses ----------

create table public.analyses (
  id uuid primary key default gen_random_uuid(),
  video_id uuid not null references public.videos (id) on delete cascade,
  model_version_id uuid not null references public.model_versions (id),
  status public.analysis_status not null default 'queued',
  mean_confidence numeric(5, 4),
  sampled_frames integer,
  fps_sampled numeric(6, 3) not null default 1,
  report_key text,
  csv_key text,
  summary_json jsonb not null default '{}'::jsonb,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index analyses_video_idx on public.analyses (video_id);
create trigger analyses_updated_at before update on public.analyses
  for each row execute function public.set_updated_at();

-- version 0 is the raw model output and is never overwritten. A surgeon's or
-- mentor's correction is saved as a new version with verified_by set.
create table public.phase_segments (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.analyses (id) on delete cascade,
  version integer not null default 0,
  phase text not null,
  start_s numeric(10, 3) not null,
  end_s numeric(10, 3) not null,
  mean_confidence numeric(5, 4),
  dominant_tool text,
  verified_by uuid references auth.users (id) on delete set null,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  constraint phase_segments_range check (end_s >= start_s),
  constraint phase_segments_verified check (version = 0 or verified_by is not null)
);
create index phase_segments_analysis_idx on public.phase_segments (analysis_id, version, start_s);

create table public.tool_segments (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.analyses (id) on delete cascade,
  tool text not null,
  start_s numeric(10, 3) not null,
  end_s numeric(10, 3) not null,
  mean_probability numeric(5, 4),
  created_at timestamptz not null default now(),
  constraint tool_segments_range check (end_s >= start_s)
);
create index tool_segments_analysis_idx on public.tool_segments (analysis_id, start_s);

create table public.scene_events (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.analyses (id) on delete cascade,
  type public.scene_event_type not null,
  start_s numeric(10, 3) not null,
  end_s numeric(10, 3) not null,
  phase_at_onset text,
  preceding_tool text,
  confirmed_by uuid references auth.users (id) on delete set null,
  confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint scene_events_range check (end_s >= start_s)
);
create index scene_events_analysis_idx on public.scene_events (analysis_id, type, start_s);

-- 1 fps probabilities for charts. Can move to Parquet in object storage later.
create table public.frame_predictions (
  analysis_id uuid not null references public.analyses (id) on delete cascade,
  second integer not null,
  phase_probs jsonb not null,
  tool_probs jsonb not null,
  primary key (analysis_id, second)
);

create table public.highlights (
  id uuid primary key default gen_random_uuid(),
  analysis_id uuid not null references public.analyses (id) on delete cascade,
  t_s numeric(10, 3) not null,
  kind text not null,                 -- phase_transition | tool_entry | tool_exit | event_onset
  title text not null,
  text text,
  sort_order integer not null default 0,
  created_at timestamptz not null default now()
);
create index highlights_analysis_idx on public.highlights (analysis_id, t_s);

-- ---------- audit log ----------

create table public.audit_log (
  id bigint generated always as identity primary key,
  actor_id uuid references auth.users (id) on delete set null,
  action text not null,               -- e.g. auth.login, video.view, video.share, video.delete, export.create
  object_type text,
  object_id text,
  ip inet,
  user_agent text,
  metadata jsonb not null default '{}'::jsonb,
  at timestamptz not null default now()
);
create index audit_log_actor_idx on public.audit_log (actor_id, at desc);
create index audit_log_object_idx on public.audit_log (object_type, object_id);

-- Login audit: Supabase Auth updates auth.users.last_sign_in_at on every
-- successful sign in, so a trigger there records the event without trusting
-- the client.
create or replace function public.audit_auth_login() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.last_sign_in_at is distinct from old.last_sign_in_at and new.last_sign_in_at is not null then
    insert into public.audit_log (actor_id, action, object_type, object_id)
    values (new.id, 'auth.login', 'user', new.id::text);
  end if;
  return new;
end
$$;

drop trigger if exists on_auth_user_login on auth.users;
create trigger on_auth_user_login after update of last_sign_in_at on auth.users
  for each row execute function public.audit_auth_login();

-- Cost monitor input (Section 12): bytes streamed are estimated by the API
-- when it serves playlists; bytes stored come from videos.size_bytes.
create table public.streaming_usage (
  id bigint generated always as identity primary key,
  video_id uuid references public.videos (id) on delete set null,
  user_id uuid references auth.users (id) on delete set null,
  bytes_estimated bigint not null,
  at timestamptz not null default now()
);
create index streaming_usage_at_idx on public.streaming_usage (at);
