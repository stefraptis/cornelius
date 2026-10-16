import type { Metadata } from "next";
import { Tags } from "lucide-react";

import { EmptyState, PageHeader } from "@/components/ui/display";
import { t } from "@/lib/i18n";

export const metadata: Metadata = { title: t("nav.annotation") };

export default function Page() {
  return (
    <>
      <PageHeader title={t("nav.annotation")} />
      <EmptyState icon={Tags} title={t("common.comingSoon")} body={t("placeholders.annotation")} />
    </>
  );
}
