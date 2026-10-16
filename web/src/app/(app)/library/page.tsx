import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { Library } from "@/components/library/library";
import { api, type StorageUsage, videosApi } from "@/lib/api";
import { t } from "@/lib/i18n";
import { getAccessToken } from "@/lib/supabase/server";

export const metadata: Metadata = { title: t("library.title") };

export default async function LibraryPage() {
  const token = await getAccessToken();
  if (!token) redirect("/login");
  const [videos, procedures] = await Promise.all([videosApi.list(token, { scope: "mine" }), api.procedures(token)]);
  let usage: StorageUsage | null = null;
  try {
    usage = await videosApi.storage(token);
  } catch {
    usage = null;
  }
  return (
    <Suspense>
      <Library initialVideos={videos} initialUsage={usage} procedures={procedures} />
    </Suspense>
  );
}
