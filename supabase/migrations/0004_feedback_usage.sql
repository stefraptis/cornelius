-- 0004 Feedback, usage events, platform admins.
-- Feedback and usage stay in our own database (EU); no third-party analytics.

create type public.feedback_category as enum ('bug', 'idea', 'question', 'other');
create type public.feedback_status as enum ('new', 'seen', 'planned', 'done', 'closed');

-- People who may see cross-account usage and feedback. Managed with the
-- service role only (SQL editor or an admin script); never through the API.
create table public.platform_admins (
  user_id uuid primary key references auth.users (id) on delete cascade,
  note text,
  created_at timestamptz not null default now()
);

create table public.feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users (id) on delete set null,
  category public.feedback_category not null default 'other',
  message text not null check (char_length(message) between 1 and 4000),
  page_url text,
  app_version text,
  user_agent text,
  screenshot_key text,
  status public.feedback_status not null default 'new',
  admin_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index feedback_created_idx on public.feedback (created_at desc);
create index feedback_user_idx on public.feedback (user_id);
create trigger feedback_updated_at before update on public.feedback
  for each row execute function public.set_updated_at();

-- One row per event: page views, feature use, durations. Properties stay
-- small and never contain patient data or free text typed by users.
create table public.usage_events (
  id bigint generated always as identity primary key,
  user_id uuid references auth.users (id) on delete set null,
  event text not null,                 -- e.g. page.view, video.play, quiz.answer
  page text,
  properties jsonb not null default '{}'::jsonb,
  duration_ms integer,
  session_id text,                     -- random id per browser tab session
  at timestamptz not null default now()
);
create index usage_events_at_idx on public.usage_events (at desc);
create index usage_events_user_at_idx on public.usage_events (user_id, at desc);
create index usage_events_event_idx on public.usage_events (event, at desc);

-- ---------- RLS ----------

alter table public.platform_admins enable row level security;
alter table public.feedback enable row level security;
alter table public.usage_events enable row level security;

create or replace function public.is_platform_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.platform_admins a where a.user_id = auth.uid())
$$;

-- A user can see whether they are an admin, nothing else.
create policy platform_admins_select on public.platform_admins for select to authenticated
  using (user_id = (select auth.uid()));

create policy feedback_insert on public.feedback for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy feedback_select on public.feedback for select to authenticated
  using (user_id = (select auth.uid()) or public.is_platform_admin());
create policy feedback_update_admin on public.feedback for update to authenticated
  using (public.is_platform_admin()) with check (public.is_platform_admin());

create policy usage_events_insert on public.usage_events for insert to authenticated
  with check (user_id = (select auth.uid()));
create policy usage_events_select on public.usage_events for select to authenticated
  using (user_id = (select auth.uid()) or public.is_platform_admin());

grant select on public.platform_admins to authenticated;
grant select, insert, update on public.feedback to authenticated;
grant select, insert on public.usage_events to authenticated;
grant all on public.platform_admins, public.feedback, public.usage_events to service_role;
grant usage, select on sequence public.usage_events_id_seq to authenticated, service_role;

-- ---------- Daily summary for the admin page ----------

create or replace view public.usage_daily as
select
  date_trunc('day', at)::date as day,
  event,
  count(*) as events,
  count(distinct user_id) as users
from public.usage_events
group by 1, 2;

grant select on public.usage_daily to authenticated, service_role;
