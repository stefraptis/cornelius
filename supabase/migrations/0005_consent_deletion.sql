-- 0005 Consent records and account deletion (GDPR mechanics, Build Guideline
-- Section 13). The legal texts themselves live in the repository
-- (web/src/legal) with a version number; this table records which version
-- each account accepted and when.

create table public.consents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  terms_version text not null,
  privacy_version text not null,
  accepted_at timestamptz not null default now(),
  ip inet,
  user_agent text
);
create index consents_user_idx on public.consents (user_id, accepted_at desc);

alter table public.consents enable row level security;
create policy consents_select on public.consents for select to authenticated
  using (user_id = (select auth.uid()));
create policy consents_insert on public.consents for insert to authenticated
  with check (user_id = (select auth.uid()));
grant select, insert on public.consents to authenticated;
grant all on public.consents to service_role;

-- Account deletion: the account row is removed at once (everything in this
-- database cascades from auth.users), and a purge job removes the objects in
-- storage. This table keeps a minimal, non-identifying trace so support can
-- answer "was my account deleted?" and so the purge can be audited.
create table public.account_deletions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,                       -- no FK: the user row is gone
  requested_at timestamptz not null default now(),
  storage_prefixes text[] not null default '{}',
  purged_at timestamptz
);
alter table public.account_deletions enable row level security;
grant all on public.account_deletions to service_role;
