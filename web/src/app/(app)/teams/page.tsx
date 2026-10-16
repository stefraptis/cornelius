import type { Metadata } from "next";
import { Users } from "lucide-react";

import { EmptyState, PageHeader } from "@/components/ui/display";
import { t } from "@/lib/i18n";

export const metadata: Metadata = { title: t("nav.teams") };

export default function Page() {
  return (
    <>
      <PageHeader title={t("nav.teams")} />
      <EmptyState icon={Users} title={t("common.comingSoon")} body={t("placeholders.teams")} />
    </>
  );
}
