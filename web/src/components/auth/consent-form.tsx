"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/input";
import { privacyApi } from "@/lib/api";
import { t } from "@/lib/i18n";
import { PRIVACY_VERSION, TERMS_VERSION } from "@/lib/legal-versions";
import { createClient } from "@/lib/supabase/client";

export function ConsentForm({ termsChanged, privacyChanged }: { termsChanged: boolean; privacyChanged: boolean }) {
  const router = useRouter();
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const docs = [termsChanged ? t("legal.terms") : null, privacyChanged ? t("legal.privacy") : null]
    .filter(Boolean)
    .join(" and ");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!accepted) return;
    setBusy(true);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) {
        router.replace("/login");
        return;
      }
      await privacyApi.accept(session.access_token, TERMS_VERSION, PRIVACY_VERSION);
      router.replace("/library");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight">{t("legal.reconsentTitle")}</h1>
      <p className="mt-1 text-sm text-text-muted">{t("legal.reconsentBody", { docs })}</p>
      <ul className="mt-6 flex flex-col gap-2 text-sm">
        {termsChanged ? (
          <li>
            <Link href="/legal/terms" target="_blank" className="text-accent hover:underline">
              {t("legal.terms")} ({TERMS_VERSION})
            </Link>
          </li>
        ) : null}
        {privacyChanged ? (
          <li>
            <Link href="/legal/privacy" target="_blank" className="text-accent hover:underline">
              {t("legal.privacy")} ({PRIVACY_VERSION})
            </Link>
          </li>
        ) : null}
      </ul>
      <form onSubmit={submit} className="mt-6 flex flex-col gap-4">
        <label className="flex items-start gap-2 text-sm">
          <Checkbox checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
          <span>{t("legal.reconsentAccept")}</span>
        </label>
        <Button type="submit" loading={busy} disabled={!accepted} className="w-full">
          {t("legal.reconsentButton")}
        </Button>
      </form>
      <form action="/auth/signout" method="post" className="mt-6 text-center">
        <Button type="submit" variant="link" className="text-xs text-text-muted">
          {t("auth.signOut")}
        </Button>
      </form>
    </div>
  );
}
