import type { Metadata } from "next";

import { MfaSettings } from "@/components/settings/mfa-settings";
import { Panel, PanelHeader } from "@/components/ui/display";
import { t } from "@/lib/i18n";

export const metadata: Metadata = { title: t("settings.security") };

export default function SecuritySettingsPage() {
  return (
    <Panel>
      <PanelHeader title={t("auth.mfa.title")} description={t("auth.mfa.requiredForAdmins")} />
      <div className="p-5">
        <MfaSettings />
      </div>
    </Panel>
  );
}
