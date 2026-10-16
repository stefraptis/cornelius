-- 0001 Accounts and hierarchy (Build Guideline, Section 4 and Section 11)
-- Conventions: UUID primary keys, created_at and updated_at, soft delete
-- (deleted_at) where a user can delete content.

create extension if not exists pgcrypto;

-- ---------- helpers ----------

create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end
$$;

-- ---------- enums ----------

create type public.org_role as enum ('org_admin', 'member');
create type public.team_role as enum ('team_owner', 'mentor', 'surgeon', 'trainee', 'annotator');
create type public.workspace_kind as enum ('personal', 'team');

-- ---------- profiles ----------

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text not null default '',
  title text,
  specialty text,
  locale text not null default 'en',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create trigger profiles_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();

-- ---------- organizations (hospitals) ----------

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  country text,
  plan text not null default 'free',
  storage_quota_gb integer not null default 100,
  video_retention_policy jsonb not null default '{"original_purge_days": 90}'::jsonb,
  allow_external_sharing boolean not null default false,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);
create trigger organizations_updated_at before update on public.organizations
  for each row execute function public.set_updated_at();

create table public.org_memberships (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role public.org_role not null default 'member',
  created_at timestamptz not null default now(),
  unique (org_id, user_id)
);
create index org_memberships_user_idx on public.org_memberships (user_id);

-- ---------- teams ----------

create table public.teams (
  id uuid primary key default gen_random_uuid(),
  org_id uuid references public.organizations (id) on delete cascade,
  name text not null,
  description text,
  created_by uuid references auth.users (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);
create index teams_org_idx on public.teams (org_id);
create trigger teams_updated_at before update on public.teams
  for each row execute function public.set_updated_at();

create table public.team_memberships (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references public.teams (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  role public.team_role not null default 'surgeon',
  created_at timestamptz not null default now(),
  unique (team_id, user_id)
);
create index team_memberships_user_idx on public.team_memberships (user_id);

-- ---------- workspaces ----------
-- A personal workspace belongs to exactly one user; a team workspace to one team.

create table public.workspaces (
  id uuid primary key default gen_random_uuid(),
  kind public.workspace_kind not null,
  owner_user_id uuid unique references auth.users (id) on delete cascade,
  team_id uuid unique references public.teams (id) on delete cascade,
  name text not null,
  storage_quota_gb integer not null default 20,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint workspaces_one_owner check (
    (kind = 'personal' and owner_user_id is not null and team_id is null) or
    (kind = 'team' and team_id is not null and owner_user_id is null)
  )
);
create trigger workspaces_updated_at before update on public.workspaces
  for each row execute function public.set_updated_at();

-- ---------- invitations ----------

create table public.invitations (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  team_id uuid references public.teams (id) on delete cascade,
  org_id uuid references public.organizations (id) on delete cascade,
  role text not null,
  token text not null unique default encode(gen_random_bytes(24), 'hex'),
  invited_by uuid references auth.users (id) on delete set null,
  expires_at timestamptz not null default now() + interval '14 days',
  accepted_at timestamptz,
  created_at timestamptz not null default now(),
  constraint invitations_target check (
    (team_id is not null and org_id is null) or (team_id is null and org_id is not null)
  )
);
create index invitations_email_idx on public.invitations (lower(email));

-- ---------- new user bootstrap ----------
-- Every new auth user gets a profile and a personal workspace. A solo surgeon
-- is simply a user with a personal workspace and no organization.

create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, full_name, locale)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'full_name', ''),
    coalesce(new.raw_user_meta_data ->> 'locale', 'en')
  )
  on conflict (id) do nothing;

  insert into public.workspaces (kind, owner_user_id, name)
  values ('personal', new.id, 'Personal')
  on conflict (owner_user_id) do nothing;

  return new;
end
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Team workspaces are created with the team.
create or replace function public.handle_new_team() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.workspaces (kind, team_id, name) values ('team', new.id, new.name)
  on conflict (team_id) do nothing;
  if new.created_by is not null then
    insert into public.team_memberships (team_id, user_id, role)
    values (new.id, new.created_by, 'team_owner')
    on conflict (team_id, user_id) do nothing;
  end if;
  return new;
end
$$;

create trigger on_team_created after insert on public.teams
  for each row execute function public.handle_new_team();

-- The creator of an organization becomes its first admin.
create or replace function public.handle_new_org() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.created_by is not null then
    insert into public.org_memberships (org_id, user_id, role)
    values (new.id, new.created_by, 'org_admin')
    on conflict (org_id, user_id) do nothing;
  end if;
  return new;
end
$$;

create trigger on_org_created after insert on public.organizations
  for each row execute function public.handle_new_org();
