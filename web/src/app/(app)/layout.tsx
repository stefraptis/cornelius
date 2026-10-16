import { redirect } from "next/navigation";
import { isRedirectError } from "next/dist/client/components/redirect-error";

import { AppShell } from "@/components/shell/app-shell";
import { api, type Me, privacyApi } from "@/lib/api";
import { PRIVACY_VERSION, TERMS_VERSION } from "@/lib/legal-versions";
import { getAccessToken, getUser } from "@/lib/supabase/server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getUser();
  const token = await getAccessToken();
  if (!user || !token) redirect("/login");

  let me: Me | null = null;
  let apiError: string | null = null;
  try {
    me = await api.me(token);
    // Re-consent gate: outdated or missing acceptance sends the user to /consent.
    const consent = await privacyApi.consent(token);
    if (consent.terms_version !== TERMS_VERSION || consent.privacy_version !== PRIVACY_VERSION) {
      redirect("/consent");
    }
  } catch (error) {
    if (isRedirectError(error)) throw error;
    apiError = error instanceof Error ? error.message : "API unreachable";
  }

  return (
    <AppShell
      me={me}
      fallback={{ email: user.email ?? null, fullName: (user.user_metadata?.full_name as string) ?? "" }}
      apiError={apiError}
    >
      {children}
    </AppShell>
  );
}
