import { redirect } from "next/navigation";

import { AppShell } from "@/components/shell/app-shell";
import { api, type Me } from "@/lib/api";
import { getAccessToken, getUser } from "@/lib/supabase/server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getUser();
  const token = await getAccessToken();
  if (!user || !token) redirect("/login");

  let me: Me | null = null;
  let apiError: string | null = null;
  try {
    me = await api.me(token);
  } catch (error) {
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
