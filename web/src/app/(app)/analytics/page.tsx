import type { Metadata } from "next";
import { BarChart3 } from "lucide-react";

import { EmptyState, PageHeader } from "@/components/ui/display";
import { t } from "@/lib/i18n";

export const metadata: Metadata = { title: t("nav.analytics") };

export default function Page() {
  return (
    <>
      <PageHeader title={t("nav.analytics")} />
      <EmptyState icon={BarChart3} title={t("common.comingSoon")} body={t("placeholders.analytics")} />
    </>
  );
}
