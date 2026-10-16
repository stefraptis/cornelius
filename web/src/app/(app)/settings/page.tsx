import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ProfileForm } from "@/components/settings/profile-form";
import { Panel, PanelHeader } from "@/components/ui/display";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { getAccessToken } from "@/lib/supabase/server";

export const metadata: Metadata = { title: t("settings.profile") };

export default async function ProfileSettingsPage() {
  const token = await getAccessToken();
  if (!token) redirect("/login");
  const me = await api.me(token);

  return (
    <div className="flex flex-col gap-6">
      <Panel>
        <PanelHeader title={t("settings.profile")} />
        <div className="p-5">
          <ProfileForm profile={me.profile} email={me.email} />
        </div>
      </Panel>

      <Panel>
        <PanelHeader title={t("settings.memberships")} />
        <div className="p-5 text-sm">
          {me.teams.length === 0 && me.organizations.length === 0 ? (
            <p className="text-text-muted">{t("settings.noMemberships")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {me.organizations.map((o) => (
                <li key={o.org_id} className="flex items-center justify-between">
                  <span>{o.org_name}</span>
                  <span className="text-xs text-text-muted">{o.role}</span>
                </li>
              ))}
              {me.teams.map((tm) => (
                <li key={tm.team_id} className="flex items-center justify-between">
                  <span>{tm.team_name}</span>
                  <span className="text-xs text-text-muted">{tm.role}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Panel>
    </div>
  );
}
