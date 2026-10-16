import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PrivacySettings } from "@/components/settings/privacy-settings";
import { api, privacyApi } from "@/lib/api";
import { t } from "@/lib/i18n";
import { getAccessToken } from "@/lib/supabase/server";

export const metadata: Metadata = { title: t("settings.privacy") };

export default async function PrivacySettingsPage() {
  const token = await getAccessToken();
  if (!token) redirect("/login");
  const [me, consent] = await Promise.all([api.me(token), privacyApi.consent(token)]);
  return <PrivacySettings email={me.email} consent={consent} />;
}
