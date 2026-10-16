-- 0003 Row-level security (Build Guideline, Section 11)
-- Every rule is enforced twice: here, and in the API. These policies are the
-- safety net. Helper functions are SECURITY DEFINER so policies can consult
-- membership tables without recursing into their own policies.

-- ---------- helper functions ----------

create or replace function public.current_user_id() returns uuid
language sql stable as $$ select auth.uid() $$;

create or replace function public.is_org_member(p_org uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.org_memberships m
    where m.org_id = p_org and m.user_id = auth.uid()
  )
$$;

create or replace function public.is_org_admin(p_org uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.org_memberships m
    where m.org_id = p_org and m.user_id = auth.uid() and m.role = 'org_admin'
  )
$$;

create or replace function public.is_team_member(p_team uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.team_memberships m
    where m.team_id = p_team and m.user_id = auth.uid()
  )
$$;

create or replace function public.team_role_of(p_team uuid) returns public.team_role
language sql stable security definer set search_path = public as $$
  select m.role from public.team_memberships m
  where m.team_id = p_team and m.user_id = auth.uid()
  limit 1
$$;

-- Team owners and org admins of the team's organization manage a team.
create or replace function public.can_manage_team(p_team uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.team_memberships m
    where m.team_id = p_team and m.user_id = auth.uid() and m.role = 'team_owner'
  ) or exists (
    select 1 from public.teams t
    where t.id = p_team and t.org_id is not null and public.is_org_admin(t.org_id)
  )
$$;

-- A team is visible to its members and to admins of its organization.
create or replace function public.can_view_team(p_team uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select public.is_team_member(p_team) or exists (
    select 1 from public.teams t
    where t.id = p_team and t.org_id is not null and public.is_org_admin(t.org_id)
  )
$$;

-- Workspace access: the owner of a personal workspace, or a member of the team.
create or replace function public.can_access_workspace(p_workspace uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.workspaces w
    where w.id = p_workspace
      and (
        w.owner_user_id = auth.uid()
        or (w.team_id is not null and public.is_team_member(w.team_id))
      )
  )
$$;

create or replace function public.is_video_owner(p_video uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.videos v
    where v.id = p_video and v.owner_user_id = auth.uid() and v.deleted_at is null
  )
$$;

-- Visibility beyond the owner comes only from video_shares.
create or replace function public.can_view_video(p_video uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select public.is_video_owner(p_video) or exists (
    select 1
    from public.video_shares s
    join public.videos v on v.id = s.video_id and v.deleted_at is null
    where s.video_id = p_video
      and (
        (s.team_id is not null and public.can_view_team(s.team_id))
        or (s.org_id is not null and public.is_org_member(s.org_id))
      )
  )
$$;

-- Permission level granted to the current user on a shared video, as text:
-- 'owner', 'annotate', 'comment', 'view', or null.
create or replace function public.video_permission(p_video uuid) returns text
language sql stable security definer set search_path = public as $$
  select case
    when public.is_video_owner(p_video) then 'owner'
    else (
      select max(s.permission::text)
      from public.video_shares s
      where s.video_id = p_video
        and (
          (s.team_id is not null and public.can_view_team(s.team_id))
          or (s.org_id is not null and public.is_org_member(s.org_id))
        )
    )
  end
$$;

-- Mentors of a team the video is shared to may correct phases.
create or replace function public.can_correct_phases(p_video uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select public.is_video_owner(p_video) or exists (
    select 1
    from public.video_shares s
    join public.team_memberships m on m.team_id = s.team_id
    where s.video_id = p_video and m.user_id = auth.uid() and m.role = 'mentor'
  )
$$;

-- Two users share context if they are in a common team or organization.
create or replace function public.shares_context_with(p_user uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select p_user = auth.uid() or exists (
    select 1 from public.team_memberships a
    join public.team_memberships b on a.team_id = b.team_id
    where a.user_id = auth.uid() and b.user_id = p_user
  ) or exists (
    select 1 from public.org_memberships a
    join public.org_memberships b on a.org_id = b.org_id
    where a.user_id = auth.uid() and b.user_id = p_user
  )
$$;

-- ---------- enable RLS everywhere ----------

alter table public.profiles enable row level security;
alter table public.organizations enable row level security;
alter table public.org_memberships enable row level security;
alter table public.teams enable row level security;
alter table public.team_memberships enable row level security;
alter table public.workspaces enable row level security;
alter table public.invitations enable row level security;
alter table public.procedures enable row level security;
alter table public.model_versions enable row level security;
alter table public.videos enable row level security;
alter table public.video_shares enable row level security;
alter table public.jobs enable row level security;
alter table public.analyses enable row level security;
alter table public.phase_segments enable row level security;
alter table public.tool_segments enable row level security;
alter table public.scene_events enable row level security;
alter table public.frame_predictions enable row level security;
alter table public.highlights enable row level security;
alter table public.audit_log enable row level security;
alter table public.streaming_usage enable row level security;

-- ---------- profiles ----------

create policy profiles_select on public.profiles for select to authenticated
  using (public.shares_context_with(id));
create policy profiles_insert on public.profiles for insert to authenticated
  with check (id = (select auth.uid()));
create policy profiles_update on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

-- ---------- organizations ----------

create policy organizations_select on public.organizations for select to authenticated
  using (deleted_at is null and (created_by = (select auth.uid()) or public.is_org_member(id)));
create policy organizations_insert on public.organizations for insert to authenticated
  with check (created_by = (select auth.uid()));
create policy organizations_update on public.organizations for update to authenticated
  using (public.is_org_admin(id)) with check (public.is_org_admin(id));

create policy org_memberships_select on public.org_memberships for select to authenticated
  using (public.is_org_member(org_id));
create policy org_memberships_insert on public.org_memberships for insert to authenticated
  with check (public.is_org_admin(org_id));
create policy org_memberships_update on public.org_memberships for update to authenticated
  using (public.is_org_admin(org_id)) with check (public.is_org_admin(org_id));
create policy org_memberships_delete on public.org_memberships for delete to authenticated
  using (public.is_org_admin(org_id) or user_id = (select auth.uid()));

-- ---------- teams ----------

-- created_by is checked inline so "insert ... returning" works before the
-- after-insert trigger adds the creator's membership.
create policy teams_select on public.teams for select to authenticated
  using (deleted_at is null and (created_by = (select auth.uid()) or public.can_view_team(id)));
create policy teams_insert on public.teams for insert to authenticated
  with check (
    created_by = (select auth.uid())
    and (org_id is null or public.is_org_admin(org_id))
  );
create policy teams_update on public.teams for update to authenticated
  using (public.can_manage_team(id)) with check (public.can_manage_team(id));

create policy team_memberships_select on public.team_memberships for select to authenticated
  using (public.can_view_team(team_id));
create policy team_memberships_insert on public.team_memberships for insert to authenticated
  with check (public.can_manage_team(team_id));
create policy team_memberships_update on public.team_memberships for update to authenticated
  using (public.can_manage_team(team_id)) with check (public.can_manage_team(team_id));
create policy team_memberships_delete on public.team_memberships for delete to authenticated
  using (public.can_manage_team(team_id) or user_id = (select auth.uid()));

-- ---------- workspaces ----------

create policy workspaces_select on public.workspaces for select to authenticated
  using (public.can_access_workspace(id));
create policy workspaces_update on public.workspaces for update to authenticated
  using (owner_user_id = (select auth.uid()) or (team_id is not null and public.can_manage_team(team_id)))
  with check (owner_user_id = (select auth.uid()) or (team_id is not null and public.can_manage_team(team_id)));

-- ---------- invitations ----------

create policy invitations_select on public.invitations for select to authenticated
  using (
    (team_id is not null and public.can_manage_team(team_id))
    or (org_id is not null and public.is_org_admin(org_id))
    or lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
create policy invitations_insert on public.invitations for insert to authenticated
  with check (
    invited_by = (select auth.uid())
    and (
      (team_id is not null and public.can_manage_team(team_id))
      or (org_id is not null and public.is_org_admin(org_id))
    )
  );
create policy invitations_delete on public.invitations for delete to authenticated
  using (
    (team_id is not null and public.can_manage_team(team_id))
    or (org_id is not null and public.is_org_admin(org_id))
  );

-- ---------- procedure registry (read-only for users) ----------

create policy procedures_select on public.procedures for select to anon, authenticated using (true);
create policy model_versions_select on public.model_versions for select to anon, authenticated using (true);

-- ---------- videos ----------

-- The owner check is inline (not only inside can_view_video) so that
-- "insert ... returning" sees the new row within the same statement.
create policy videos_select on public.videos for select to authenticated
  using (deleted_at is null and (owner_user_id = (select auth.uid()) or public.can_view_video(id)));
create policy videos_insert on public.videos for insert to authenticated
  with check (
    owner_user_id = (select auth.uid())
    and public.can_access_workspace(workspace_id)
  );
create policy videos_update on public.videos for update to authenticated
  using (owner_user_id = (select auth.uid()))
  with check (owner_user_id = (select auth.uid()));
-- Hard delete is reserved for the service role (purge job). Users soft delete.

create policy video_shares_select on public.video_shares for select to authenticated
  using (public.can_view_video(video_id));
create policy video_shares_insert on public.video_shares for insert to authenticated
  with check (public.is_video_owner(video_id) and created_by = (select auth.uid()));
create policy video_shares_update on public.video_shares for update to authenticated
  using (public.is_video_owner(video_id)) with check (public.is_video_owner(video_id));
create policy video_shares_delete on public.video_shares for delete to authenticated
  using (public.is_video_owner(video_id));

-- ---------- jobs (read-only for users; workers use the service role) ----------

create policy jobs_select on public.jobs for select to authenticated
  using (video_id is not null and public.can_view_video(video_id));

-- ---------- analysis outputs ----------

create policy analyses_select on public.analyses for select to authenticated
  using (public.can_view_video(video_id));

create policy phase_segments_select on public.phase_segments for select to authenticated
  using (exists (select 1 from public.analyses a where a.id = analysis_id and public.can_view_video(a.video_id)));
-- Corrections: only verified versions, only by owner or team mentor, never version 0.
create policy phase_segments_insert on public.phase_segments for insert to authenticated
  with check (
    version > 0
    and verified_by = (select auth.uid())
    and exists (select 1 from public.analyses a where a.id = analysis_id and public.can_correct_phases(a.video_id))
  );

create policy tool_segments_select on public.tool_segments for select to authenticated
  using (exists (select 1 from public.analyses a where a.id = analysis_id and public.can_view_video(a.video_id)));

create policy scene_events_select on public.scene_events for select to authenticated
  using (exists (select 1 from public.analyses a where a.id = analysis_id and public.can_view_video(a.video_id)));
create policy scene_events_confirm on public.scene_events for update to authenticated
  using (exists (select 1 from public.analyses a where a.id = analysis_id and public.can_correct_phases(a.video_id)))
  with check (exists (select 1 from public.analyses a where a.id = analysis_id and public.can_correct_phases(a.video_id)));

create policy frame_predictions_select on public.frame_predictions for select to authenticated
  using (exists (select 1 from public.analyses a where a.id = analysis_id and public.can_view_video(a.video_id)));

create policy highlights_select on public.highlights for select to authenticated
  using (exists (select 1 from public.analyses a where a.id = analysis_id and public.can_view_video(a.video_id)));

-- ---------- audit log ----------
-- Users may record their own actions and read their own trail. Org-wide
-- reporting is done by the API with the service role (M4).

create policy audit_log_insert on public.audit_log for insert to authenticated
  with check (actor_id = (select auth.uid()));
create policy audit_log_select on public.audit_log for select to authenticated
  using (actor_id = (select auth.uid()));

-- streaming_usage is written by the API with the service role only.

-- Job claiming is for workers only.
revoke execute on function public.claim_next_job(public.job_type[], text) from public, anon, authenticated;
grant execute on function public.claim_next_job(public.job_type[], text) to service_role;

-- ---------- grants ----------
-- Supabase grants ALL table privileges to anon and authenticated by default
-- and relies on RLS for filtering. Here the defaults are revoked first so each
-- role holds exactly the privileges the permission matrix allows: an operation
-- a user must never perform (hard delete of a video, writing model output)
-- fails with "permission denied" instead of silently affecting zero rows.

revoke all on all tables in schema public from anon, authenticated;

grant select, insert, update on public.profiles to authenticated;
grant select, insert, update on public.organizations to authenticated;
grant select, insert, update, delete on public.org_memberships to authenticated;
grant select, insert, update on public.teams to authenticated;
grant select, insert, update, delete on public.team_memberships to authenticated;
grant select, update on public.workspaces to authenticated;
grant select, insert, delete on public.invitations to authenticated;
grant select on public.procedures, public.model_versions to anon, authenticated;
grant select, insert, update on public.videos to authenticated;
grant select, insert, update, delete on public.video_shares to authenticated;
grant select on public.jobs to authenticated;
grant select on public.analyses to authenticated;
grant select, insert on public.phase_segments to authenticated;
grant select on public.tool_segments to authenticated;
grant select, update on public.scene_events to authenticated;
grant select on public.frame_predictions to authenticated;
grant select on public.highlights to authenticated;
grant select, insert on public.audit_log to authenticated;
grant all on all tables in schema public to service_role;
grant all on all sequences in schema public to service_role;
