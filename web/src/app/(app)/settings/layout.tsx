import { SettingsNav } from "@/components/settings/settings-nav";
import { PageHeader } from "@/components/ui/display";
import { t } from "@/lib/i18n";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader title={t("settings.title")} />
      <div className="grid gap-8 md:grid-cols-[200px_1fr]">
        <SettingsNav />
        <div className="min-w-0 max-w-2xl">{children}</div>
      </div>
    </>
  );
}
