import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { ConsentForm } from "@/components/auth/consent-form";
import { privacyApi } from "@/lib/api";
import { t } from "@/lib/i18n";
import { PRIVACY_VERSION, TERMS_VERSION } from "@/lib/legal-versions";
import { getAccessToken } from "@/lib/supabase/server";

export const metadata: Metadata = { title: t("legal.reconsentTitle") };

export default async function ConsentPage() {
  const token = await getAccessToken();
  if (!token) redirect("/login");
  const consent = await privacyApi.consent(token);
  const termsChanged = consent.terms_version !== TERMS_VERSION;
  const privacyChanged = consent.privacy_version !== PRIVACY_VERSION;
  if (!termsChanged && !privacyChanged) redirect("/library");

  return <ConsentForm termsChanged={termsChanged} privacyChanged={privacyChanged} />;
}
