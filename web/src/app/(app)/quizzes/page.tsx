import type { Metadata } from "next";
import { GraduationCap } from "lucide-react";

import { EmptyState, PageHeader } from "@/components/ui/display";
import { t } from "@/lib/i18n";

export const metadata: Metadata = { title: t("nav.quizzes") };

export default function Page() {
  return (
    <>
      <PageHeader title={t("nav.quizzes")} />
      <EmptyState icon={GraduationCap} title={t("common.comingSoon")} body={t("placeholders.quizzes")} />
    </>
  );
}
