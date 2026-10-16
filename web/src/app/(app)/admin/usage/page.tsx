import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { AdminUsage } from "@/components/admin/admin-usage";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import { getAccessToken } from "@/lib/supabase/server";

export const metadata: Metadata = { title: t("admin.title") };

export default async function AdminUsagePage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const token = await getAccessToken();
  if (!token) redirect("/login");
  const me = await api.me(token);
  if (!me.platform_admin) notFound();

  const { days: daysParam } = await searchParams;
  const days = [7, 30, 90].includes(Number(daysParam)) ? Number(daysParam) : 30;
  const [summary, feedback] = await Promise.all([api.adminUsage(token, days), api.adminFeedback(token)]);

  return <AdminUsage summary={summary} feedback={feedback} />;
}
